"""HTTP surface: the UI's exact contract, exercised against a live server."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from trainapp import server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = cls.tmp.name
        cls.httpd = server.build_server("127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)
        if cls.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = cls.prev
        cls.tmp.cleanup()

    def call(self, path: str, method: str = "GET", body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode()
                return response.status, json.loads(raw) if raw.strip().startswith(("{", "[")) else raw
        except urllib.error.HTTPError as err:
            try:
                raw = err.read().decode()
            finally:
                err.close()
            return err.code, json.loads(raw) if raw.strip().startswith("{") else raw

    def test_health(self) -> None:
        status, body = self.call("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertIn(body["platform"], ("Linux", "Windows"))

    def test_ui_is_served(self) -> None:
        status, body = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn("Train App", body)
        status, _ = self.call("/app.js")
        self.assertEqual(status, 200)

    def test_unknown_route_is_404(self) -> None:
        status, body = self.call("/api/nope")
        self.assertEqual(status, 404)
        self.assertIn("no route", body["error"])

    def test_toolchains_report_python(self) -> None:
        status, body = self.call("/api/toolchains")
        self.assertEqual(status, 200)
        python = next(t for t in body["toolchains"] if t["language"] == "python")
        self.assertTrue(python["available"], python)

    def test_node_lifecycle(self) -> None:
        status, created = self.call("/api/nodes", "POST",
                                    {"name": "lifecycle.py", "code": "print('first')\n"})
        self.assertEqual(status, 200, created)
        self.assertEqual(created["language"], "python")

        status, _ = self.call("/api/nodes", "POST", {"name": "lifecycle.py", "code": ""})
        self.assertEqual(status, 409)

        status, body = self.call("/api/nodes")
        self.assertIn("lifecycle.py", [n["name"] for n in body["nodes"]])

        status, _ = self.call("/api/nodes/lifecycle.py", "PUT",
                              {"code": "print('second')\n"})
        self.assertEqual(status, 200)

        status, run = self.call("/api/nodes/lifecycle.py/run", "POST", {})
        self.assertEqual(status, 200)
        self.assertTrue(run["run"]["ok"], run)
        self.assertIn("second", run["run"]["stdout"])
        self.assertEqual(run["run"]["exit_code"], 0)

        status, _ = self.call("/api/nodes/lifecycle.py", "DELETE")
        self.assertEqual(status, 200)
        status, _ = self.call("/api/nodes/lifecycle.py")
        self.assertEqual(status, 404)

    def test_failing_run_reports_the_error_text(self) -> None:
        status, _ = self.call("/api/nodes", "POST",
                              {"name": "fails.py", "code": "raise SystemExit('kaput')\n"})
        self.assertEqual(status, 200)
        status, run = self.call("/api/nodes/fails.py/run", "POST", {})
        self.assertEqual(status, 200)
        self.assertFalse(run["run"]["ok"])
        self.assertIn("kaput", run["run"]["stderr"])
        self.call("/api/nodes/fails.py", "DELETE")

    def test_bad_node_names_are_refused(self) -> None:
        for name in ("../escape.py", "noextension", "a b.py"):
            status, body = self.call("/api/nodes", "POST", {"name": name, "code": ""})
            self.assertGreaterEqual(status, 400, f"{name} was accepted")
            self.assertIn("error", body)

    def test_dataset_endpoint(self) -> None:
        status, body = self.call("/api/dataset")
        self.assertEqual(status, 200)
        self.assertIn("rows", body)
        status, meta = self.call("/api/dataset/export", "POST", {})
        self.assertEqual(status, 200)
        self.assertIn("train_examples", meta)

    def test_train_status_and_guarded_start(self) -> None:
        status, body = self.call("/api/train/status")
        self.assertEqual(status, 200)
        self.assertIn("state", body)
        status, body = self.call("/api/train/start", "POST", {"backend": "agent"})
        self.assertEqual(status, 409)
        self.assertIn("dataset is empty", body["error"])

    def test_library_endpoint(self) -> None:
        status, body = self.call("/api/library")
        self.assertEqual(status, 200)
        self.assertIn("library", body)
        self.assertIn("judge", body)
        self.assertIn("confirmed", body["library"])

    def test_library_build_endpoint(self) -> None:
        status, body = self.call("/api/library/build", "POST", {})
        self.assertEqual(status, 200)
        self.assertIn("index", body)
        self.assertIn("total", body["index"])

    def test_validation_status_endpoint(self) -> None:
        status, body = self.call("/api/library/validate/status")
        self.assertEqual(status, 200)
        self.assertIn("state", body)

    def test_tournament_status_endpoint(self) -> None:
        status, body = self.call("/api/tournament/status")
        self.assertEqual(status, 200)
        self.assertIn("state", body)

    def test_tournament_without_confirmed_tasks_is_409(self) -> None:
        status, body = self.call("/api/tournament/start", "POST", {"max_tasks": 1})
        self.assertEqual(status, 409)
        self.assertIn("error", body)

    def test_growth_status_endpoint(self) -> None:
        status, body = self.call("/api/library/grow/status")
        self.assertEqual(status, 200)
        self.assertIn("state", body)

    def test_growth_without_confirmed_tasks_is_409(self) -> None:
        status, body = self.call("/api/library/grow", "POST", {"seeds": 1})
        self.assertEqual(status, 409)
        self.assertIn("no confirmed runnable tasks", body["error"])

    def test_config_is_readable(self) -> None:
        status, body = self.call("/api/config")
        self.assertEqual(status, 200)
        self.assertIn("training", body["config"])
        self.assertIn("llm", body["config"])

    def test_static_traversal_is_not_served(self) -> None:
        status, _ = self.call("/..%2f..%2fetc%2fpasswd")
        self.assertIn(status, (400, 404))


if __name__ == "__main__":
    unittest.main()
