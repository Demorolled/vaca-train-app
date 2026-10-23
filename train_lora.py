#!/usr/bin/env python3
"""train_lora — SFT or ORPO over the train-app datasets.

SFT reads verified-fix / winner rows (`{instruction, input, output}`).
ORPO reads judged preference pairs (`{prompt, chosen, rejected}`) and trains
without a reference model, so the 2×12 GB agent can fit it next to a 1.5B–14B
policy.

Requires torch, transformers, peft, datasets (bitsandbytes for 4-bit).
Nothing is installed automatically — a missing dependency is reported plainly.

    # SFT
    python train_lora.py --train data/dataset/train.jsonl --model ... --out ...
    # ORPO over judged pairs
    python train_lora.py --mode orpo --pairs data/dataset/pairs_train.jsonl \\
        --val-pairs data/dataset/pairs_val.jsonl --model ... --out ...
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

PROMPT_TEMPLATE = (
    "### Instruction\n{instruction}\n\n"
    "### Input\n{input}\n\n"
    "### Response\n{output}"
)

KEEP_COLUMNS = {"input_ids", "attention_mask", "labels"}


def drop_extra_columns(columns: list[str]) -> list[str]:
    """Columns to remove after tokenising.

    The collator can only pad tensors; a leftover string column (`source`, the
    capture metadata) makes it raise at the first batch, so this stays pure and
    unit-tested rather than buried in a GPU-only code path.
    """
    return [c for c in columns if c not in KEEP_COLUMNS]


def load_rows(path: str) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("output"):
            rows.append(row)
    return rows


def load_pairs(path: str) -> list[dict]:
    """Preference rows; a pair without both sides is not trainable."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("prompt") and row.get("chosen", "").strip() and row.get("rejected", "").strip():
            rows.append(row)
    return rows


def to_text(row: dict) -> str:
    return PROMPT_TEMPLATE.format(
        instruction=row.get("instruction", ""),
        input=row.get("input", ""),
        output=row.get("output", ""),
    )


def use_4bit(no_4bit: bool, cuda: bool, has_bitsandbytes: bool) -> bool:
    """4-bit only when it is both wanted and actually installable.

    A missing bitsandbytes used to surface as a hard failure inside
    `from_pretrained`, which on a 12 GB card is worse than just running bf16.
    """
    return (not no_4bit) and cuda and has_bitsandbytes


def preference_accuracy(margins: list[float]) -> dict:
    """Held-out preference accuracy from `logp(chosen) - logp(rejected)`.

    A margin above zero means the policy already prefers the judged winner, so
    this is the one number that says whether an ORPO round learned anything.
    Pure and testable: the metric is computed from margins, not from GPU state.
    """
    if not margins:
        return {"pairs": 0, "accuracy": 0.0, "mean_margin": 0.0}
    wins = sum(1 for m in margins if m > 0)
    return {
        "pairs": len(margins),
        "accuracy": round(wins / len(margins), 4),
        "mean_margin": round(sum(margins) / len(margins), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Train on verified rows or judged pairs")
    parser.add_argument("--mode", choices=("sft", "orpo"), default="sft")
    parser.add_argument("--train", default="")
    parser.add_argument("--val", default="")
    parser.add_argument("--pairs", default="")
    parser.add_argument("--val-pairs", default="")
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-steps", type=int, default=120)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--seq-len", type=int, default=2048)
    parser.add_argument("--lora-r", type=int, default=8)
    parser.add_argument("--lora-alpha", type=int, default=16)
    parser.add_argument("--orpo-lambda", type=float, default=0.1)
    parser.add_argument("--no-4bit", action="store_true")
    parser.add_argument("--init-adapter", default="",
                        help="continue training from an existing adapter (for loops)")
    args = parser.parse_args()

    if args.mode == "orpo" and not args.pairs:
        print("train_lora: --mode orpo needs --pairs", file=sys.stderr)
        return 2
    if args.mode == "sft" and not args.train:
        print("train_lora: --mode sft needs --train", file=sys.stderr)
        return 2

    try:
        import torch
        import torch.nn.functional as F
        from datasets import Dataset
        from peft import (LoraConfig, PeftModel, get_peft_model,
                          prepare_model_for_kbit_training)
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, DataCollatorForLanguageModeling,
            Trainer, TrainingArguments,
        )
    except ImportError as err:
        print(f"train_lora: missing dependency: {err}", file=sys.stderr)
        print("install: pip install torch transformers peft datasets accelerate "
              "bitsandbytes", file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_rows = load_rows(args.train) if args.mode == "sft" and args.train else []
    pair_rows = load_pairs(args.pairs) if args.mode == "orpo" else []
    if args.mode == "sft" and not train_rows:
        print(f"train_lora: no rows in {args.train}", file=sys.stderr)
        return 2
    if args.mode == "orpo" and not pair_rows:
        print(f"train_lora: no usable pairs in {args.pairs}", file=sys.stderr)
        return 2
    val_rows = (load_rows(args.val) if args.val and Path(args.val).exists() else []) \
        if args.mode == "sft" else []
    val_pairs = (load_pairs(args.val_pairs)
                 if args.val_pairs and Path(args.val_pairs).exists() else [])
    print(f"train_lora: mode={args.mode} train={len(train_rows) or len(pair_rows)} "
          f"val={len(val_rows) or len(val_pairs)}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    has_bnb = importlib.util.find_spec("bitsandbytes") is not None
    quantize = use_4bit(args.no_4bit, torch.cuda.is_available(), has_bnb)
    if torch.cuda.is_available() and not args.no_4bit and not has_bnb:
        print("train_lora: bitsandbytes missing — bf16 instead of 4-bit", flush=True)
    model_kwargs: dict = {"trust_remote_code": True}
    if quantize:
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["device_map"] = "auto"
    elif torch.cuda.is_available():
        model_kwargs["torch_dtype"] = torch.bfloat16
        model_kwargs["device_map"] = "auto"

    print(f"train_lora: model={args.model} 4bit={quantize} "
          f"cuda={torch.cuda.is_available()}", flush=True)
    model = AutoModelForCausalLM.from_pretrained(args.model, **model_kwargs)
    if quantize:
        model = prepare_model_for_kbit_training(model)

    if args.init_adapter:
        # A loop round must build on the previous round, not restart from base.
        model = PeftModel.from_pretrained(model, args.init_adapter, is_trainable=True)
        print(f"train_lora: continuing from {args.init_adapter}", flush=True)
    else:
        model = get_peft_model(model, LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
        ))
    model.print_trainable_parameters()

    # Activations, not the adapter, set the memory ceiling: ORPO holds two graphs
    # at once, and an SFT row now carries a scaffold prompt with its siblings in
    # context. Checkpointing cuts activations ~10x for a ~30% slowdown, which is
    # what makes seq 1024 fit a 12 GB card that a busy desktop is also using.
    model.config.use_cache = False
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
    try:
        model.gradient_checkpointing_enable(
            gradient_checkpointing_kwargs={"use_reentrant": False})
    except TypeError:
        model.gradient_checkpointing_enable()
    print("train_lora: gradient checkpointing on", flush=True)

    # Trainer's own eval step calls the model with the dataset's raw columns. For
    # SFT those are `input_ids`/`labels`, which the model understands; for pairs
    # the columns are `chosen_input_ids`/`rejected_*`, so Trainer's eval would
    # call Qwen2 without `input_ids` and fail *after* a successful train. Pairs are
    # therefore evaluated by `evaluate_pairs()` below, not by the Trainer loop.
    eval_with_trainer = bool(val_rows) and args.mode == "sft"
    training_args = TrainingArguments(
        output_dir=str(out_dir / "checkpoints"),
        max_steps=args.max_steps,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        eval_accumulation_steps=8,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        logging_steps=1,
        save_steps=max(20, args.max_steps // 3),
        save_total_limit=2,
        eval_strategy="steps" if eval_with_trainer else "no",
        eval_steps=max(20, args.max_steps // 3) if eval_with_trainer else None,
        report_to=[],
        remove_unused_columns=False,
        bf16=torch.cuda.is_available(),
        optim="paged_adamw_8bit" if quantize else "adamw_torch",
    )

    meta = {
        "base_model": args.model,
        "mode": args.mode,
        "max_steps": args.max_steps,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "init_adapter": args.init_adapter,
    }

    if args.mode == "orpo":
        # ── ORPO ────────────────────────────────────────────────────────────
        def encode(prompt: str, response: str) -> tuple[list[int], list[int], list[int]]:
            prompt_ids = tokenizer(prompt, add_special_tokens=False).input_ids
            response_ids = tokenizer(response, add_special_tokens=False).input_ids
            if not response_ids:
                response_ids = [tokenizer.eos_token_id]
            room = max(2, args.seq_len - len(prompt_ids))
            if room < 2:
                prompt_ids = prompt_ids[: args.seq_len - 2]
                room = 2
            response_ids = response_ids[:room]
            input_ids = prompt_ids + response_ids
            labels = [-100] * len(prompt_ids) + response_ids
            attention = [1] * len(input_ids)
            return input_ids, attention, labels

        pad_id = tokenizer.pad_token_id or tokenizer.eos_token_id

        def pad(rows: list[tuple[list[int], list[int], list[int]]]) -> dict:
            width = max(len(r[0]) for r in rows)
            ids, mask, labels = [], [], []
            for input_ids, attention, label_ids in rows:
                pad_len = width - len(input_ids)
                ids.append(input_ids + [pad_id] * pad_len)
                mask.append(attention + [0] * pad_len)
                labels.append(label_ids + [-100] * pad_len)
            return {"input_ids": torch.tensor(ids), "attention_mask": torch.tensor(mask),
                    "labels": torch.tensor(labels)}

        class PreferenceCollator:
            def __call__(self, features: list[dict]) -> dict:
                chosen = [encode(f["prompt"], f["chosen"]) for f in features]
                rejected = [encode(f["prompt"], f["rejected"]) for f in features]
                batch = {}
                for name, rows in (("chosen", chosen), ("rejected", rejected)):
                    for key, value in pad(rows).items():
                        batch[f"{name}_{key}"] = value
                return batch

        def sequence_logp(logits, labels, chunk: int = 128):
            """Mean log-probability of the RESPONSE tokens only.

            The log-softmax runs in fp32 but only over `chunk` positions at a
            time. A single `log_softmax(logits.float())` over a 1024-token
            sequence at this vocabulary is ~1.2 GB per call and both calls stay
            alive for backward, which is exactly how the first 12 GB GPU run
            died; chunking keeps the peak at a few tens of MB without dropping
            to bf16 precision for the verdict-burning margin.
            """
            logits = logits[:, :-1, :]
            labels = labels[:, 1:]
            mask = labels != -100
            gathered = torch.zeros(labels.shape, dtype=torch.float32,
                                   device=logits.device)
            for start in range(0, labels.shape[1], chunk):
                stop = start + chunk
                piece = torch.log_softmax(logits[:, start:stop, :].float(), dim=-1)
                targets = labels[:, start:stop].clamp(min=0).unsqueeze(-1)
                gathered[:, start:stop] = piece.gather(-1, targets).squeeze(-1)
                del piece
            counts = mask.sum(-1).clamp(min=1)
            return (gathered * mask).sum(-1) / counts

        class ORPOTrainer(Trainer):
            lambda_or = args.orpo_lambda

            def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
                chosen = {k: inputs[f"chosen_{k}"] for k in ("input_ids", "attention_mask", "labels")}
                rejected = {k: inputs[f"rejected_{k}"] for k in ("input_ids", "attention_mask", "labels")}
                out_c = model(**chosen)
                out_r = model(**rejected)
                lp_c = sequence_logp(out_c.logits, chosen["labels"])
                lp_r = sequence_logp(out_r.logits, rejected["labels"])

                sft = -lp_c.mean()
                # log-odds ratio, clamped so log1p(-exp(lp)) stays finite
                odds_c = lp_c.clamp(max=-1e-6)
                odds_r = lp_r.clamp(max=-1e-6)
                log_odds = (odds_c - torch.log1p(-torch.exp(odds_c))) - \
                           (odds_r - torch.log1p(-torch.exp(odds_r)))
                or_loss = -F.logsigmoid(log_odds).mean()
                loss = sft + self.lambda_or * or_loss
                return (loss, out_c) if return_outputs else loss

        train_ds = Dataset.from_list([{"prompt": r["prompt"], "chosen": r["chosen"],
                                       "rejected": r["rejected"]} for r in pair_rows])

        def evaluate_pairs(rows: list[dict]) -> dict:
            """Held-out preference accuracy for the CURRENT weights.

            Called before and after training, because "did the round help?" is
            only answerable against the untrained policy on the same pairs.
            """
            was_training = model.training
            model.eval()
            margins: list[float] = []
            with torch.no_grad():
                for row in rows:
                    scores = []
                    for side in ("chosen", "rejected"):
                        batch = {k: v.to(model.device)
                                 for k, v in pad([encode(row["prompt"], row[side])]).items()}
                        scores.append(float(sequence_logp(
                            model(**batch).logits, batch["labels"]).mean()))
                    margins.append(scores[0] - scores[1])
            if was_training:
                model.train()
            return preference_accuracy(margins)

        if val_pairs:
            meta["val_before"] = evaluate_pairs(val_pairs)
            print(f"train_lora: held-out before training {meta['val_before']}", flush=True)

        trainer = ORPOTrainer(
            model=model,
            args=training_args,
            train_dataset=train_ds,
            data_collator=PreferenceCollator(),
        )
        meta.update({"train_pairs": len(pair_rows), "val_pairs": len(val_pairs),
                     "orpo_lambda": args.orpo_lambda})
    else:
        # ── SFT ─────────────────────────────────────────────────────────────
        def tokenize(batch: dict) -> dict:
            encoded = tokenizer(
                [to_text({k: batch[k][i] for k in ("instruction", "input", "output")})
                 for i in range(len(batch["instruction"]))],
                truncation=True, max_length=args.seq_len, padding=False,
            )
            # Labels are left to the collator: it clones input_ids and pads them
            # with -100. Setting ragged labels here made the eval collator fail
            # ("Unable to create tensor") as soon as a val batch mixed lengths.
            return encoded

        def build_dataset(rows: list[dict]):
            ds = Dataset.from_list(rows).map(tokenize, batched=True)
            return ds.remove_columns(drop_extra_columns(ds.column_names))

        train_ds = build_dataset(train_rows)
        val_ds = build_dataset(val_rows) if val_rows else None
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=train_ds,
            eval_dataset=val_ds,
            data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False),
        )
        meta.update({"train_rows": len(train_rows), "val_rows": len(val_rows)})

    trainer.train()

    if args.mode == "orpo" and val_pairs:
        meta["val"] = evaluate_pairs(val_pairs)
        meta["val_improved"] = (meta["val"]["accuracy"]
                                > meta["val_before"]["accuracy"])
        print(f"train_lora: held-out after training {meta['val']} "
              f"(improved={meta['val_improved']})", flush=True)

    adapter_dir = out_dir / "adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    meta["adapter"] = str(adapter_dir)
    (out_dir / "train_meta.json").write_text(json.dumps(meta, indent=2) + "\n",
                                             encoding="utf-8")
    print(f"train_lora: adapter written to {adapter_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
