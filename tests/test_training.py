"""Training launcher: agent-box script shape, dataset guard, job tracking."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from train_lora import (
    KEEP_COLUMNS, drop_extra_columns, load_pairs, preference_accuracy, to_text,
    use_4bit,
)
from trainapp import capture, config, training


class TrainingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.prev = os.environ.get("TRAIN_APP_DATA")
        os.environ["TRAIN_APP_DATA"] = self.tmp.name
        self.cfg = config.load()

    def tearDown(self) -> None:
        if self.prev is None:
            os.environ.pop("TRAIN_APP_DATA", None)
        else:
            os.environ["TRAIN_APP_DATA"] = self.prev
        self.tmp.cleanup()

    def add_row(self, n: int = 1) -> None:
        ok, reason = capture.append_row(capture.make_fix_row(
            language="python", filename=f"n{n}.py", platform="Linux",
            command="python3 n.py", exit_code=1, error_output="boom",
            before="print(1/0)\n", after=f"print({n})\n",
        ))
        self.assertTrue(ok, reason)

    def test_agent_script_copies_then_runs_on_the_agent_box(self) -> None:
        self.add_row()
        meta = capture.export_dataset()
        script = training.build_agent_script(self.cfg, meta)

        agent = self.cfg["training"]["agent"]
        self.assertIn(f"{agent['user']}@{agent['host']}", script)
        self.assertIn("scp", script)
        self.assertIn("ssh", script)
        self.assertIn("BatchMode=yes", script)
        self.assertIn(agent["python"], script)
        self.assertIn("train_lora.py", script)
        self.assertIn(Path(meta["train_path"]).name, script)
        self.assertIn(Path(meta["val_path"]).name, script)
        self.assertIn("mkdir -p", script)
        # The remote side must not try to install anything.
        self.assertNotIn("pip install", script)

    def test_local_command_runs_the_shipped_trainer(self) -> None:
        self.add_row()
        meta = capture.export_dataset()
        argv = training.build_local_command(self.cfg, meta, Path(self.tmp.name) / "out")
        self.assertEqual(argv[1], str(config.APP_ROOT / "train_lora.py"))
        self.assertIn("--max-steps", argv)
        self.assertIn(str(meta["train_path"]), argv)

    def test_local_orpo_command_uses_the_pairs(self) -> None:
        meta = {"train_path": "/tmp/pairs_train.jsonl",
                "val_path": "/tmp/pairs_val.jsonl"}
        argv = training.build_local_command(self.cfg, meta, Path(self.tmp.name) / "o",
                                            mode="orpo")
        self.assertIn("--mode", argv)
        self.assertEqual(argv[argv.index("--mode") + 1], "orpo")
        self.assertIn("--pairs", argv)
        self.assertIn("--val-pairs", argv)
        self.assertIn("/tmp/pairs_train.jsonl", argv)

    def test_agent_orpo_script_copies_pairs_and_passes_mode(self) -> None:
        meta = {"train_path": "/tmp/pairs_train.jsonl",
                "val_path": "/tmp/pairs_val.jsonl"}
        script = training.build_agent_script(self.cfg, meta, mode="orpo")
        self.assertIn("pairs_train.jsonl", script)
        self.assertIn("--mode", script)
        self.assertIn("orpo", script)
        self.assertIn("--pairs", script)
        self.assertNotIn("--train", script)

    def test_orpo_start_without_pairs_reports_it(self) -> None:
        result = training.start(backend="agent", mode="orpo")
        self.assertIn("no preference pairs", result["error"])

    def test_status_includes_pair_stats(self) -> None:
        status = training.status()
        self.assertIn("pairs", status)
        self.assertIn("pairs", status["pairs"])

    def test_trainer_drops_non_tensor_columns(self) -> None:
        # Regression: `source`/`meta` in a JSONL row reached the collator and
        # killed training at step 0 with "Unable to create tensor".
        extra = drop_extra_columns(["input_ids", "attention_mask", "labels", "source", "meta"])
        self.assertEqual(extra, ["source", "meta"])
        self.assertEqual(drop_extra_columns(list(KEEP_COLUMNS)), [])

    def test_trainer_prompt_uses_the_capture_fields(self) -> None:
        text = to_text({"instruction": "fix it", "input": "boom", "output": "print(1)"})
        self.assertIn("### Instruction\nfix it", text)
        self.assertIn("### Input\nboom", text)
        self.assertIn("### Response\nprint(1)", text)

    def test_trainer_script_exists_and_declares_dependencies(self) -> None:
        trainer = config.APP_ROOT / "train_lora.py"
        self.assertTrue(trainer.exists())
        text = trainer.read_text(encoding="utf-8")
        for dep in ("transformers", "peft", "datasets"):
            self.assertIn(dep, text)

    def test_empty_dataset_is_refused_with_the_reason(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            training.ensure_dataset()
        self.assertIn("dataset is empty", str(ctx.exception))

    def test_start_with_empty_dataset_returns_error_not_a_job(self) -> None:
        result = training.start(backend="agent")
        self.assertIn("dataset is empty", result["error"])
        self.assertEqual(result["state"], "idle")
        self.assertIsNone(result["pid"])

    def test_status_shape(self) -> None:
        status = training.status()
        for key in ("state", "backend", "model", "log", "tail", "dataset"):
            self.assertIn(key, status)
        self.assertIn("rows", status["dataset"])

    def test_stop_without_a_run_is_honest(self) -> None:
        self.assertIn("no training run is active", training.stop()["error"])
        self.assertEqual(training.status()["state"], "idle")


class HeldOutPairTests(unittest.TestCase):
    """The ORPO round is only worth keeping if it improves on unseen pairs."""

    def test_accuracy_counts_only_positive_margins(self) -> None:
        result = preference_accuracy([0.4, 0.1, 0.0, -0.3])
        self.assertEqual(result["pairs"], 4)
        self.assertEqual(result["accuracy"], 0.5)
        self.assertAlmostEqual(result["mean_margin"], 0.05, places=6)

    def test_a_tie_is_not_a_win(self) -> None:
        self.assertEqual(preference_accuracy([0.0])["accuracy"], 0.0)

    def test_no_pairs_reports_zero_instead_of_dividing_by_zero(self) -> None:
        self.assertEqual(preference_accuracy([]),
                         {"pairs": 0, "accuracy": 0.0, "mean_margin": 0.0})

    def test_4bit_needs_bitsandbytes(self) -> None:
        self.assertTrue(use_4bit(False, True, True))
        self.assertFalse(use_4bit(False, True, False))
        self.assertFalse(use_4bit(False, False, True))
        self.assertFalse(use_4bit(True, True, True))

    def test_incomplete_pairs_are_not_trainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pairs.jsonl"
            path.write_text(
                '{"prompt":"p","chosen":"a","rejected":"b"}\n'
                '{"prompt":"p","chosen":"a","rejected":"   "}\n'
                '{"prompt":"p","rejected":"b"}\n',
                encoding="utf-8")
            self.assertEqual(len(load_pairs(str(path))), 1)


if __name__ == "__main__":
    unittest.main()
