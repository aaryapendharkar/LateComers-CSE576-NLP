"""Generator: prompt building, robust JSON parsing, VLM wrapper. OWNER: Person 1.

The exact prompts live in configs/prompts/ so runs are reproducible; if you
change a prompt, make a new file (generator_v2.txt) instead of editing v1.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from ..common.answer_match import parse_number
from ..common.config import resolve


@dataclass
class PageInput:
    page_id: str
    text: Optional[str] = None        # P1, P3
    image_path: Optional[str] = None  # P2, P3


@dataclass
class GenerationResult:
    answer_raw: str
    answer: Optional[str]
    cited: list[str] = field(default_factory=list)


def load_prompt(path: str) -> str:
    return resolve(path).read_text(encoding="utf-8")


def format_pages_block(pages: list[PageInput]) -> str:
    """Text part of the context. Images are attached separately in page order."""
    parts = []
    for p in pages:
        body = p.text if p.text is not None else "(see the attached image for this page)"
        parts.append(f"[PAGE {p.page_id}]\n{body}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

_JSON_OBJ = re.compile(r"\{.*?\}", re.DOTALL)


def parse_generation(raw: str, allowed_pages: Optional[list[str]] = None) -> GenerationResult:
    """Pull {"answer": ..., "cited_pages": [...]} out of model output, robustly.

    Handles code fences, extra prose, single quotes, a bare number, and
    "[PAGE id]" mentions when cited_pages is missing.
    """
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)   # Qwen3.5 reasoning block
    raw = re.sub(r"^.*?</think>", "", raw, flags=re.DOTALL)           # opening tag cut off
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    obj = None
    candidates = [text] + _JSON_OBJ.findall(text)
    for c in candidates:
        for attempt in (c, c.replace("'", '"')):
            try:
                v = json.loads(attempt)
                if isinstance(v, dict):
                    obj = v
                    break
            except json.JSONDecodeError:
                continue
        if obj is not None:
            break

    if obj is not None:
        ans = obj.get("answer")
        ans = None if ans is None else str(ans).strip()
        cited = obj.get("cited_pages") or obj.get("cited") or []
        if isinstance(cited, str):
            cited = [cited]
    else:
        m = re.search(r'"?answer"?\s*[:=]\s*"?([^\s",}]+)', text, re.IGNORECASE)
        ans = m.group(1).strip() if m else (str(parse_number(text)) if parse_number(text) is not None else None)
        cited = []
    if not cited:
        cited = re.findall(r"\[?PAGE\s+([^\]\s,]+)\]?", raw)
    cited = [str(c).replace("[PAGE", "").strip(" []") for c in cited]
    if allowed_pages is not None:
        cited = [c for c in cited if c in allowed_pages]
    return GenerationResult(raw, ans, list(dict.fromkeys(cited)))


# ---------------------------------------------------------------------------
# Real generator (Hugging Face VLM)
# ---------------------------------------------------------------------------


class VLMGenerator:
    """Greedy-decoding vision-language generator.

    Written for Qwen3.5 (Qwen/Qwen3.5-9B, fallback Qwen/Qwen3.5-4B): natively
    multimodal, loaded through the transformers auto classes and the chat template.
    Qwen3.5 "thinks" by default; we switch thinking OFF (enable_thinking=False) so
    the reply is the JSON answer, and parse_generation strips any <think> block.
    """

    def __init__(self, model_name: str, prompt_file: str, closed_book_prompt_file: str,
                 device: str = "cuda", dtype: str = "bfloat16", max_new_tokens: int = 256):
        self.name = model_name
        self.prompt = load_prompt(prompt_file)
        self.closed_book_prompt = load_prompt(closed_book_prompt_file)
        self.device, self.dtype, self.max_new_tokens = device, dtype, max_new_tokens
        self._model = self._proc = None

    def _load(self):
        if self._model is None:
            import torch
            import transformers
            from transformers import AutoProcessor

            self._proc = AutoProcessor.from_pretrained(self.name)
            last_err = None
            for cls_name in ("AutoModelForImageTextToText", "AutoModelForMultimodalLM"):
                cls = getattr(transformers, cls_name, None)
                if cls is None:
                    continue
                try:
                    self._model = cls.from_pretrained(
                        self.name, dtype=getattr(torch, self.dtype), device_map=self.device).eval()
                    break
                except (ValueError, TypeError) as e:  # model type not registered for this auto class
                    last_err = e
            if self._model is None:
                raise RuntimeError(f"could not load {self.name}; upgrade transformers "
                                   f"(pip install -U transformers). Last error: {last_err}")
        return self._model, self._proc

    def _messages(self, question: str, pages: list[PageInput]) -> tuple[list[dict], list]:
        from PIL import Image

        if not pages:
            return [{"role": "user", "content": [
                {"type": "text", "text": self.closed_book_prompt.format(question=question)}]}], []
        content: list[dict] = []
        images = []
        for p in pages:
            content.append({"type": "text", "text": f"[PAGE {p.page_id}]"})
            if p.image_path:
                images.append(Image.open(p.image_path).convert("RGB"))
                content.append({"type": "image"})
            if p.text is not None:
                content.append({"type": "text", "text": p.text})
        page_ids = ", ".join(p.page_id for p in pages)
        content.append({"type": "text", "text": self.prompt.format(question=question, page_ids=page_ids)})
        return [{"role": "user", "content": content}], images

    def generate(self, question: str, pages: list[PageInput]) -> GenerationResult:
        import torch

        model, proc = self._load()
        messages, images = self._messages(question, pages)
        prompt = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=False,
                                          enable_thinking=False)
        inputs = proc(text=[prompt], images=images or None, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        raw = proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        return parse_generation(raw, allowed_pages=[p.page_id for p in pages])
