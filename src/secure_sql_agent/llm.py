"""OpenRouter client (OpenAI-compatible). One place for model calls so cost and latency are measured the same way
for every vendor. Truncated output is an error, never a silent empty answer."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from openai import OpenAI


class LLMError(Exception):
    pass


@dataclass
class Completion:
    text: str
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float


def load_model_ids(path: str = "config/models.yaml") -> dict[str, dict]:
    return yaml.safe_load(Path(path).read_text())


class LLM:
    def __init__(self, model_id: str, api_key: str, base_url: str = "https://openrouter.ai/api/v1",
                 temperature: float = 0, max_tokens: int = 1200):
        self.model_id, self.temperature, self.max_tokens = model_id, temperature, max_tokens
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=2)

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> Completion:
        t0 = time.perf_counter()
        try:
            r = self._client.chat.completions.create(
                model=self.model_id, temperature=self.temperature, max_tokens=max_tokens or self.max_tokens,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                extra_body={"usage": {"include": True}},  # OpenRouter returns the dollar cost
            )
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"{type(e).__name__}: {str(e)[:200]}") from e
        choice = r.choices[0]
        if choice.finish_reason == "length":
            raise LLMError(f"output truncated at max_tokens ({self.model_id})")
        text = (choice.message.content or "").strip()
        if not text:
            raise LLMError(f"empty completion (finish_reason={choice.finish_reason})")
        u = r.usage
        extra = (u.model_extra or {}) if u else {}
        return Completion(text, float(extra.get("cost") or 0.0), u.prompt_tokens if u else 0,
                          u.completion_tokens if u else 0, (time.perf_counter() - t0) * 1000)
