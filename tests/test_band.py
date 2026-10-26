"""The band: players, toggles, seats, the leader, and the copy of every build."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import band, builder, config


class BandCase(unittest.TestCase):
    """A scratch config and data root, so no test touches the real band."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = str(self.root / "data")
        self.addCleanup(self.restore)
        self.path = self.root / "config.json"
        patcher = mock.patch.object(config, "CONFIG_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev


class PlayerTests(BandCase):
    def test_the_default_band_is_the_14b_leading_three_players(self) -> None:
        summary = band.summary()
        self.assertEqual(summary["leader"]["name"], "llm")
        self.assertIn("14b", summary["leader"]["model"])
        self.assertEqual([m["name"] for m in summary["members"]], ["llm", "builder", "judge"])
        self.assertTrue(all(m["enabled"] for m in summary["members"]))
        self.assertEqual(summary["seats"],
                         {"coder": "llm", "builder": "builder", "judge": "judge"})

    def test_a_player_can_be_added_with_no_key_at_all(self) -> None:
        summary = band.add("lmstudio", "qwen2.5-coder-7b", "http://127.0.0.1:1234/v1")
        added = [m for m in summary["members"] if m["name"] == "lmstudio"][0]
        self.assertTrue(added["enabled"])
        self.assertEqual(added["seats"], [])
        self.assertFalse(added["needs_key"])
        # The leader does not move because a new player arrived.
        self.assertEqual(summary["leader"]["name"], "llm")

    def test_a_hosted_player_records_that_it_has_a_key_but_never_the_key(self) -> None:
        band.add("openrouter", "qwen/qwen3-coder:free", "https://openrouter.ai/api/v1",
                 api_key="sk-or-secret")
        summary = band.summary()
        added = [m for m in summary["members"] if m["name"] == "openrouter"][0]
        self.assertTrue(added["needs_key"])
        self.assertNotIn("sk-or-secret", json.dumps(summary))

    def test_a_player_without_a_model_name_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            band.add("nameless", "", "http://127.0.0.1:11434/v1")

    def test_a_player_without_a_url_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            band.add("nowhere", "some-model", "")

    def test_a_name_that_already_exists_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            band.add("llm", "another-14b", "http://127.0.0.1:11434/v1")

    def test_a_name_with_punctuation_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            band.add("my model!", "m", "http://127.0.0.1:11434/v1")

    def test_an_added_player_can_be_switched_off_and_back_on(self) -> None:
        band.add("spare", "m", "http://127.0.0.1:11434/v1")
        self.assertFalse(band.toggle("spare", False)["members"][-1]["enabled"])
        self.assertTrue(band.toggle("spare", True)["members"][-1]["enabled"])

    def test_a_seated_player_cannot_be_switched_off(self) -> None:
        with self.assertRaises(KeyError) as caught:
            band.toggle("judge", False)
        self.assertIn("judge seat", str(caught.exception))

    def test_the_leader_cannot_be_switched_off(self) -> None:
        with self.assertRaises(KeyError) as caught:
            band.toggle("llm", False)
        self.assertIn("leads the band", str(caught.exception))

    def test_a_seat_moves_to_the_player_that_takes_it(self) -> None:
        band.add("small", "qwen2.5-coder-7b", "http://127.0.0.1:11434/v1")
        summary = band.seat("builder", "small")
        self.assertEqual(summary["seats"]["builder"], "small")
        holders = {m["name"]: m["seats"] for m in summary["members"]}
        self.assertEqual(holders["small"], ["builder"])
        self.assertEqual(holders["builder"], [])

    def test_a_switched_off_player_cannot_take_a_seat(self) -> None:
        band.add("sleeping", "m", "http://127.0.0.1:11434/v1")
        band.toggle("sleeping", False)
        with self.assertRaises(KeyError):
            band.seat("coder", "sleeping")

    def test_the_leader_is_set_and_must_be_a_player_that_is_on(self) -> None:
        band.add("backup", "qwen3-coder-30b", "http://example:11434/v1")
        self.assertEqual(band.set_leader("backup")["leader"]["name"], "backup")
        with self.assertRaises(KeyError):
            band.set_leader("nobody")

    def test_a_leader_cannot_be_removed(self) -> None:
        with self.assertRaises(KeyError) as caught:
            band.remove("llm")
        self.assertIn("leads the band", str(caught.exception))

    def test_a_seated_player_cannot_be_removed(self) -> None:
        with self.assertRaises(KeyError) as caught:
            band.remove("judge")
        self.assertIn("seat", str(caught.exception))

    def test_an_added_player_that_holds_nothing_can_be_removed(self) -> None:
        band.add("visitor", "m", "http://127.0.0.1:11434/v1")
        band.remove("visitor")
        self.assertNotIn("visitor", [m["name"] for m in band.members()])
        # And the file no longer carries it.
        self.assertNotIn("visitor", self.path.read_text(encoding="utf-8"))

    def test_a_bundled_connection_is_switched_off_not_deleted(self) -> None:
        with self.assertRaises(KeyError):
            config.forget("judge")


class LeaderClientTests(BandCase):
    def test_the_builder_uses_the_leader_when_no_player_is_named(self) -> None:
        band.add("tiny", "tiny-coder", "http://127.0.0.1:9999/v1")
        band.set_leader("tiny")
        chat = builder.chat_for()
        self.assertEqual(chat.model, "tiny-coder")
        self.assertEqual(chat.url, "http://127.0.0.1:9999/v1")

    def test_an_added_player_carries_its_own_wire_protocol_and_key(self) -> None:
        band.add("hosted", "big-coder", "https://example.com/v1", kind="openai",
                 api_key="k-123", temperature=0.5)
        chat = builder.chat_for("hosted")
        self.assertEqual(chat.kind, "openai")
        self.assertEqual(chat.api_key, "k-123")
        self.assertEqual(chat.temperature, 0.5)

    def test_a_switched_off_player_is_refused_by_the_builder(self) -> None:
        band.add("off", "m", "http://127.0.0.1:11434/v1")
        band.toggle("off", False)
        with self.assertRaises(KeyError):
            builder.chat_for("off")

    def test_a_keyless_player_sends_no_authorization_header(self) -> None:
        band.add("local", "local-coder", "http://127.0.0.1:11434/v1")
        sent: list[dict] = []

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        def capture(request, timeout=None):
            sent.append({"url": request.full_url, "headers": dict(request.headers)})
            return Reply()

        with mock.patch("urllib.request.urlopen", capture):
            builder.chat_for("local").ask("sys", "user")
        self.assertNotIn("Authorization", sent[0]["headers"])

    def test_a_keyed_player_sends_its_key(self) -> None:
        band.add("hosted2", "m", "https://example.com/v1", api_key="k-9")
        sent: list[dict] = []

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        def capture(request, timeout=None):
            sent.append(dict(request.headers))
            return Reply()

        with mock.patch("urllib.request.urlopen", capture):
            builder.chat_for("hosted2").ask("sys", "user")
        self.assertEqual(sent[0].get("Authorization"), "Bearer k-9")


class ProbeTests(BandCase):
    def test_a_player_that_answers_and_serves_the_model_is_up(self) -> None:
        band.add("local", "qwen2.5-coder-7b", "http://127.0.0.1:11434/v1")

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"models": [{"name": "qwen2.5-coder-7b"}]}).encode()

        with mock.patch("urllib.request.urlopen", lambda *a, **k: Reply()):
            result = band.probe("local")
        self.assertTrue(result["up"])
        self.assertTrue(result["served"])

    def test_a_player_that_does_not_serve_the_model_says_so(self) -> None:
        band.add("local", "a-model-nobody-pulled", "http://127.0.0.1:11434/v1")

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"models": [{"name": "something-else"}]}).encode()

        with mock.patch("urllib.request.urlopen", lambda *a, **k: Reply()):
            result = band.probe("local")
        self.assertTrue(result["up"])
        self.assertFalse(result["served"])

    def test_an_openai_server_that_lists_models_under_data_is_understood(self) -> None:
        band.add("hosted", "big-coder", "https://example.com/v1")

        class Reply:
            def __init__(self, payload: dict) -> None:
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps(self.payload).encode()

        def openai_only(request, timeout=None):
            if request.full_url.endswith("/api/tags"):
                raise OSError("404 not found")
            return Reply({"data": [{"id": "big-coder"}]})

        with mock.patch("urllib.request.urlopen", openai_only):
            result = band.probe("hosted")
        self.assertTrue(result["up"])
        self.assertTrue(result["served"])
        self.assertEqual(result["models"], ["big-coder"])

    def test_an_answer_without_a_model_list_is_not_read_as_the_model_missing(self) -> None:
        band.add("odd", "a-model", "http://127.0.0.1:8177/v1")

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"data": [{"id": "a-model"}]}).encode()

        # The native probe URL answers with something that is not a model list;
        # the OpenAI URL is then the one that counts.
        with mock.patch("urllib.request.urlopen", lambda *a, **k: Reply()):
            result = band.probe("odd")
        self.assertTrue(result["up"])
        self.assertTrue(result["served"])

    def test_an_unreachable_player_reports_the_error_not_a_crash(self) -> None:
        def refuse(*_a, **_k):
            raise OSError("connection refused")

        with mock.patch("urllib.request.urlopen", refuse):
            result = band.probe("llm")
        self.assertFalse(result["up"])
        self.assertIn("connection refused", result["error"])


RECORD = {
    "at": "2026-10-25T16:00:00Z",
    "model": "qwen2.5-coder-14b-uncensored-q4:latest",
    "task": {"id": "brief/0", "language": "python"},
    "attempts": [
        {"n": 1, "plan_reply": "{}", "plan_reasoning": "it is trivial",
         "files_reply": "FILE: main.py\n```python\nprint(41)\n```",
         "files": [{"path": "main.py", "content": "print(41)\n"}],
         "build": {"ok": False, "error": "expected 42"}},
        {"n": 2, "plan_reply": "{}", "files_reply": "fixed",
         "files": [{"path": "main.py", "content": "print(42)\n"},
                   {"path": "util.py", "content": "X = 1\n"}],
         "build": {"ok": True}},
    ],
    "files": [{"path": "main.py", "content": "print(42)\n"},
              {"path": "util.py", "content": "X = 1\n"}],
    "build": {"ok": True, "command": "python3 main.py", "exit_code": 0,
              "stdout": "42\n", "error": ""},
}


class CopyTests(BandCase):
    def test_a_build_is_copied_whole(self) -> None:
        result = band.copy_build(RECORD)
        target = Path(result["path"])
        self.assertTrue(target.is_dir())
        saved = json.loads((target / "record.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["build"]["command"], "python3 main.py")
        self.assertEqual((target / "files" / "main.py").read_text(encoding="utf-8"),
                         "print(42)\n")
        self.assertEqual((target / "files" / "util.py").read_text(encoding="utf-8"),
                         "X = 1\n")
        self.assertIn("42", (target / "build.txt").read_text(encoding="utf-8"))
        plan = (target / "attempt-1-plan.md").read_text(encoding="utf-8")
        self.assertIn("it is trivial", plan)
        # The set that failed before the fix is kept; the one that shipped is not
        # written twice.
        self.assertEqual((target / "attempt-1" / "files" / "main.py")
                         .read_text(encoding="utf-8"), "print(41)\n")
        self.assertFalse((target / "attempt-2" / "files").exists())
        self.assertEqual(result["files"], 3)
        self.assertEqual(result["attempts"], 2)

    def test_a_path_that_escapes_the_copy_is_never_written(self) -> None:
        record = dict(RECORD)
        record["files"] = [{"path": "../escape.py", "content": "boom\n"}]
        record["attempts"] = []
        result = band.copy_build(record)
        self.assertEqual(result["files"], 0)
        self.assertFalse((self.root / "escape.py").exists())
        self.assertFalse((Path(result["path"]).parent.parent / "escape.py").exists())

    def test_two_builds_of_one_task_in_one_second_do_not_overwrite_each_other(self) -> None:
        first = band.copy_build(RECORD)
        second = band.copy_build(RECORD)
        self.assertNotEqual(first["path"], second["path"])
        self.assertTrue(Path(first["path"]).is_dir())
        self.assertTrue(Path(second["path"]).is_dir())

    def test_a_series_copies_every_build_it_runs(self) -> None:
        band.set_copy_builds(True)
        record = {"ok": True, "runs": 1, "files": [{"path": "main.py", "content": "x\n"}],
                  "conventions": True, "at": "2026-10-25T16:01:00Z",
                  "model": "fake-14b", "task": {"id": "brief/0"}, "attempts": [],
                  "build": {"ok": True}}
        specs = [{"id": "app/1", "language": "python", "brief": "b"},
                 {"id": "app/2", "language": "python", "brief": "b"}]
        with mock.patch.object(builder, "specs_from_library", return_value=specs), \
             mock.patch.object(builder, "chat_for", return_value=mock.Mock(model="fake-14b")), \
             mock.patch.object(builder, "build_app", return_value=record), \
             mock.patch.object(builder, "write_pool", return_value={"added": 1}), \
             mock.patch.object(builder.scaffold, "write", return_value={}):
            builder.start(brief="b")
            builder._THREAD.join(timeout=10)
        copies = list((config.data_dir() / "builds").glob("*/*/record.json"))
        self.assertEqual(len(copies), 2)
        final = builder.status()
        self.assertEqual(final["state"], "done")
        self.assertTrue(all(r["copy"] for r in final["records"]))
        for path in final["records"]:
            self.assertTrue(Path(path["copy"]).is_dir())

    def test_the_copy_switch_turns_the_copy_off(self) -> None:
        self.assertTrue(band.copy_builds())
        self.assertFalse(band.set_copy_builds(False)["copy_builds"])
        record = {"ok": True, "runs": 1, "files": [], "conventions": False,
                  "at": "2026-10-25T16:02:00Z", "model": "fake-14b",
                  "task": {"id": "brief/0"}, "attempts": [], "build": {}}
        specs = [{"id": "app/1", "language": "python", "brief": "b"}]
        with mock.patch.object(builder, "specs_from_library", return_value=specs), \
             mock.patch.object(builder, "chat_for", return_value=mock.Mock(model="fake-14b")), \
             mock.patch.object(builder, "build_app", return_value=record), \
             mock.patch.object(builder, "write_pool", return_value={"added": 1}), \
             mock.patch.object(builder.scaffold, "write", return_value={}):
            builder.start(brief="b")
            builder._THREAD.join(timeout=10)
        self.assertFalse((config.data_dir() / "builds").exists())
        self.assertEqual(builder.status()["records"][0]["copy"], "")


if __name__ == "__main__":
    unittest.main()
