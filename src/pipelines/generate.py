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


def shorten_page_text(text: str, max_chars: int) -> str:
    """Fit a page into ``max_chars`` WITHOUT cutting the table.

    The markdown table (the evidence every attack edits) is always kept whole;
    only the prose before/after it is trimmed (the part furthest from the table
    goes first). Pages without a table are cut at the end.
    """
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    lines = text.split("\n")
    rows = [i for i, l in enumerate(lines) if l.strip().startswith("|")]
    if not rows:
        return text[:max_chars].rstrip() + " [...]"
    start, end = rows[0], rows[-1]
    while start > 0 and lines[start - 1].strip() and not lines[start - 1].strip().startswith("|") \
            and len(lines[start - 1]) < 120:      # keep short title / unit lines glued to the table
        start -= 1
    pre, table, post = "\n".join(lines[:start]), "\n".join(lines[start:end + 1]), "\n".join(lines[end + 1:])
    budget = max(0, max_chars - len(table) - 20)
    keep_pre = min(len(pre), budget * 2 // 3)
    keep_post = min(len(post), budget - keep_pre)
    keep_pre = min(len(pre), budget - keep_post)
    pre = ("[...] " + pre[len(pre) - keep_pre:].lstrip()) if keep_pre < len(pre) else pre
    post = (post[:keep_post].rstrip() + " [...]") if keep_post < len(post) else post
    return "\n".join(x for x in (pre, table, post) if x)


def fit_image(img, max_pixels: int):
    """Downscale a page image to at most ``max_pixels`` (keeps aspect ratio)."""
    w, h = img.size
    if max_pixels <= 0 or w * h <= max_pixels:
        return img
    scale = (max_pixels / (w * h)) ** 0.5
    return img.resize((max(28, int(w * scale)), max(28, int(h * scale))))


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
                 device: str = "cuda", dtype: str = "bfloat16", max_new_tokens: int = 256,
                 max_page_chars: int = 0, max_image_pixels: int = 0):
        self.name = model_name
        self.max_page_chars, self.max_image_pixels = max_page_chars, max_image_pixels
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

    def _messages(self, question: str, pages: list[PageInput], shrink: int = 1) -> tuple[list[dict], list]:
        from PIL import Image

        if not pages:
            return [{"role": "user", "content": [
                {"type": "text", "text": self.closed_book_prompt.format(question=question)}]}], []
        content: list[dict] = []
        images = []
        for p in pages:
            content.append({"type": "text", "text": f"[PAGE {p.page_id}]"})
            if p.image_path:
                img = Image.open(p.image_path).convert("RGB")
                images.append(fit_image(img, self.max_image_pixels // (shrink * shrink)))
                content.append({"type": "image"})
            if p.text is not None:
                content.append({"type": "text", "text": shorten_page_text(p.text, self.max_page_chars // shrink)})
        page_ids = ", ".join(p.page_id for p in pages)
        content.append({"type": "text", "text": self.prompt.format(question=question, page_ids=page_ids)})
        return [{"role": "user", "content": content}], images

    def _generate_once(self, question: str, pages: list[PageInput], shrink: int) -> str:
        import torch

        model, proc = self._load()
        messages, images = self._messages(question, pages, shrink)
        prompt = proc.apply_chat_template(messages, add_generation_prompt=True, tokenize=False,
                                          enable_thinking=False)
        inputs = proc(text=[prompt], images=images or None, return_tensors="pt").to(model.device)
        try:
            with torch.no_grad():
                out = model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
            return proc.batch_decode(out[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)[0]
        finally:
            del inputs
            torch.cuda.empty_cache()

    def generate(self, question: str, pages: list[PageInput]) -> GenerationResult:
        """On GPU out-of-memory, retry with pages shrunk 2x, then 4x (prose only; tables stay whole).
        If it still fails, log an empty answer instead of crashing the whole run."""
        import torch

        for shrink in (1, 2, 4):
            try:
                raw = self._generate_once(question, pages, shrink)
                if shrink > 1:
                    raw = f"[shrunk x{shrink} after OOM] " + raw
                return parse_generation(raw, allowed_pages=[p.page_id for p in pages])
            except torch.OutOfMemoryError:
                torch.cuda.empty_cache()
        return GenerationResult("[OOM: no answer]", None, [])
