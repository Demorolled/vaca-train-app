"""Roles: which connection does the talking, the building, and the judging."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from trainapp import builder, config, repair


class RoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "config.json"
        self.patch = mock.patch.object(config, "CONFIG_PATH", self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_the_three_roles_exist_by_default(self) -> None:
        roles = config.roles()
        self.assertEqual(sorted(roles), ["builder", "coder", "judge"])

    def test_a_role_resolves_to_its_connection_settings(self) -> None:
        settings = config.connection("builder")
        self.assertEqual(settings["name"], "builder")
        self.assertTrue(settings["model"])
        self.assertEqual(settings["role"], "builder")

    def test_an_unknown_role_raises_instead_of_defaulting(self) -> None:
        with self.assertRaises(KeyError):
            config.connection("therapist")

    def test_a_role_can_be_pointed_at_another_connection(self) -> None:
        self.path.write_text(json.dumps({"other": {"url": "http://x/v1",
                                                   "model": "big-model-70b"}}),
                             encoding="utf-8")
        roles = config.assign("builder", "other")
        self.assertEqual(roles["builder"], "other")
        self.assertEqual(config.connection("builder")["model"], "big-model-70b")

    def test_assigning_to_a_connection_that_does_not_exist_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            config.assign("builder", "not-a-connection")

    def test_every_connection_is_listed_with_its_model(self) -> None:
        names = config.connections()
        self.assertIn("llm", names)
        self.assertIn("model", names["llm"])


class ClientRoleTests(unittest.TestCase):
    def test_the_coder_client_follows_its_role(self) -> None:
        with mock.patch.object(config, "connection",
                               return_value={"role": "coder", "name": "llm",
                                             "model": "coder-14b",
                                             "url": "http://127.0.0.1:11434",
                                             "timeout_s": 30, "num_ctx": 8192}):
            client = repair.OllamaClient()
        self.assertEqual(client.model, "coder-14b")

    def test_the_builder_client_follows_its_role(self) -> None:
        with mock.patch.object(config, "connection",
                               return_value={"role": "builder", "name": "builder",
                                             "model": "builder-30b",
                                             "url": "http://example:11434/v1",
                                             "kind": "ollama", "think": True,
                                             "timeout_s": 60, "max_tokens": 100}):
            chat = builder.Chat()
        self.assertEqual(chat.model, "builder-30b")
        self.assertEqual(chat.kind, "ollama")
        self.assertTrue(chat.think)

    def test_a_local_builder_asks_for_a_context_big_enough_for_the_plan(self) -> None:
        sent: list[dict] = []

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"message": {"content": "ok"}, "model": "m"}).encode()

        def capture(request, timeout=None):
            sent.append(json.loads(request.data.decode()))
            return Reply()

        with mock.patch.object(config, "connection",
                               return_value={"role": "builder", "name": "builder2",
                                             "model": "small-7b",
                                             "url": "http://example:11434/v1",
                                             "kind": "ollama", "think": False,
                                             "timeout_s": 60, "max_tokens": 100}), \
             mock.patch("urllib.request.urlopen", capture):
            builder.Chat(num_ctx=8192).ask("sys", "user")
            no_ctx = builder.Chat()
            no_ctx.ask("sys", "user")
        self.assertEqual(sent[0]["options"]["num_ctx"], 8192)
        self.assertNotIn("num_ctx", sent[1]["options"])

    def test_a_coding_model_can_be_asked_without_thinking(self) -> None:
        with mock.patch.object(config, "connection",
                               return_value={"role": "builder", "name": "builder",
                                             "model": "coder-30b",
                                             "url": "http://example:11434/v1",
                                             "kind": "ollama", "think": False,
                                             "timeout_s": 60, "max_tokens": 100}):
            chat = builder.Chat()
        self.assertFalse(chat.think)


if __name__ == "__main__":
    unittest.main()
