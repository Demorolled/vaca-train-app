"""The relay seat: a prompt on disk, an answer by hand, no endpoint anywhere."""
from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from trainapp import band, builder, config, relay


class RelayCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.addCleanup(self.restore)
        patcher = mock.patch.object(config, "CONFIG_PATH",
                                    Path(self.tmp.name) / "config.json")
        patcher.start()
        self.addCleanup(patcher.stop)

    def restore(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev


class HandoffTests(RelayCase):
    def test_a_prompt_lands_in_the_outbox_with_its_text(self) -> None:
        request = relay.submit("be the architect", "build a printer")
        self.assertTrue((relay.root() / "outbox" / f"{request['id']}.json").is_file())
        waiting = relay.pending()
        self.assertEqual([r["id"] for r in waiting], [request["id"]])
        text = relay.prompt_text(relay.show(request["id"]))
        self.assertIn("[system]\nbe the architect", text)
        self.assertIn("build a printer", text)

    def test_a_json_seat_asks_for_json_in_the_paste(self) -> None:
        request = relay.submit("qa", "review this", json_object=True)
        self.assertIn("[answer with JSON only]", relay.prompt_text(request))
        plain = relay.submit("qa", "x")
        self.assertFalse(relay.show(plain["id"])["json"])

    def test_answering_unblocks_the_caller(self) -> None:
        seat = relay.RelaySeat(timeout_s=10, poll_s=0.02)

        box: dict = {}

        def take_the_seat() -> None:
            box["reply"] = seat.ask("dev", "write the file")

        worker = threading.Thread(target=take_the_seat, daemon=True)
        worker.start()
        for _ in range(200):
            if relay.pending():
                break
            time.sleep(0.02)
        pending = relay.pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["system"], "dev")
        relay.answer(pending[0]["id"], "FILE: main.py\n```python\nprint(1)\n```")
        worker.join(timeout=10)
        self.assertIn("print(1)", box["reply"]["content"])
        self.assertEqual(box["reply"]["model"], "relay")
        # Both halves move to the archive, so the next prompt is not confused
        # with this one and --pending is empty again.
        self.assertEqual(relay.pending(), [])
        self.assertTrue((relay.root() / "archive" / "inbox"
                         / f"{pending[0]['id']}.json").is_file())

    def test_nobody_answering_times_out_with_the_command_to_fix_it(self) -> None:
        with self.assertRaises(relay.RelayTimeout) as caught:
            relay.RelaySeat(timeout_s=0.15, poll_s=0.02).ask("dev", "nobody home")
        self.assertIn("--pending", str(caught.exception))

    def test_answering_a_request_that_is_not_pending_is_refused(self) -> None:
        with self.assertRaises(relay.RelayError):
            relay.answer("20260101T000000-dead", "hello")

    def test_an_answered_request_is_no_longer_pending(self) -> None:
        request = relay.submit("dev", "write it")
        relay.answer(request["id"], "done")
        self.assertEqual(relay.pending(), [])
        # The seat can still collect it, and the collection clears the exchange.
        self.assertEqual(relay.wait(request["id"], timeout_s=1, poll_s=0.01)["content"],
                         "done")

    def test_a_request_id_that_is_a_path_is_refused(self) -> None:
        with self.assertRaises(relay.RelayError):
            relay.show("../../etc/passwd")


class BandWiringTests(RelayCase):
    def test_a_relay_player_needs_no_url(self) -> None:
        summary = band.add("webbrain", "chat-ui-model", "", kind="relay")
        added = [m for m in summary["members"] if m["name"] == "webbrain"][0]
        self.assertEqual(added["model"], "chat-ui-model")
        self.assertEqual(added["url"], "")

    def test_a_socket_player_still_needs_a_url(self) -> None:
        with self.assertRaises(KeyError):
            band.add("nowhere", "some-model", "")

    def test_the_builder_hands_a_relay_player_a_seat_not_a_socket(self) -> None:
        band.add("webbrain", "chat-ui-model", "", kind="relay")
        seat = builder.chat_for("webbrain")
        self.assertIsInstance(seat, relay.RelaySeat)
        self.assertEqual(seat.model, "chat-ui-model")

    def test_probing_a_relay_player_says_there_is_no_endpoint_to_probe(self) -> None:
        band.add("webbrain", "chat-ui-model", "", kind="relay")
        result = band.probe("webbrain")
        self.assertTrue(result["up"])
        self.assertIn("manual seat", result["error"])

    def test_a_relay_seat_can_be_the_leader(self) -> None:
        band.add("webbrain", "chat-ui-model", "", kind="relay")
        band.set_leader("webbrain")
        self.assertEqual(builder.chat_for().model, "chat-ui-model")


if __name__ == "__main__":
    unittest.main()
