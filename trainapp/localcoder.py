"""localcoder — serve a local HF model (optionally + a LoRA adapter) as a coder.

The app's coder is normally an Ollama model on a URL. A freshly trained adapter
is a PEFT directory that nothing serves yet, and starting a whole inference
server to score it would be a second moving part. This class is the smallest
thing that fits the existing seam: it exposes the same `complete(prompt)`
method as `repair.OllamaClient`, so the battery and the growth loop can point at
weights on disk without knowing anything about transformers.

torch/transformers/peft are imported lazily: the rest of the app (and its tests)
must keep working on a machine that has none of them.
"""
from __future__ import annotations

import threading

SYSTEM = (
    "You write a single file that solves the given task. Reply with the "
    "complete file only — no markdown fence, no explanation."
)


class LocalCoder:
    """Greedy, chat-templated generation from a local model plus optional adapter."""

    def __init__(self, model: str, adapter: str = "", max_new_tokens: int = 700,
                 dtype: str = "bfloat16", device_map: str = "auto",
                 temperature: float = 0.0, top_p: float = 1.0) -> None:
        self.model = model
        self.adapter = adapter
        self.max_new_tokens = max_new_tokens
        self.dtype = dtype
        self.device_map = device_map
        # Greedy by default: scoring a capability wants one reproducible answer.
        # A gate that grades "does it still keep the contract" wants draws from
        # the sampling the app actually serves at, so it passes 0.7/0.9 and a
        # second call is a second sample rather than the same decode again.
        self.temperature = temperature
        self.top_p = top_p
        self._tok = None
        self._net = None
        self._lock = threading.Lock()

    @property
    def label(self) -> str:
        return f"{self.model}{'+' + self.adapter if self.adapter else ''}"

    def _load(self):
        if self._net is not None:
            return self._tok, self._net
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(self.model)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token
        net = AutoModelForCausalLM.from_pretrained(
            self.model, dtype=getattr(torch, self.dtype), device_map=self.device_map)
        if self.adapter:
            from peft import PeftModel
            net = PeftModel.from_pretrained(net, self.adapter)
        net.eval()
        self._tok, self._net = tok, net
        return tok, net

    def complete(self, prompt: str) -> str:
        import torch

        tok, net = self._load()
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt}]
        text = tok.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=True)
        inputs = tok(text, return_tensors="pt").to(net.device)
        sampling: dict = {"max_new_tokens": self.max_new_tokens, "do_sample": False}
        if self.temperature > 0:
            sampling.update(do_sample=True, temperature=self.temperature,
                            top_p=self.top_p)
        with self._lock, torch.no_grad():
            out = net.generate(**inputs, **sampling, pad_token_id=tok.pad_token_id)
        new_tokens = out[0][inputs["input_ids"].shape[1]:]
        return tok.decode(new_tokens, skip_special_tokens=True)

    def close(self) -> None:
        import torch

        self._net = None
        self._tok = None
        torch.cuda.empty_cache()
