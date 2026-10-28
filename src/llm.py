"""OpenAI-compatible LLM client (stdlib only).

Supports MiniMax / StepFun / any OpenAI-compatible chat endpoint.
Configure with env vars (see .env.example):

    LLM_PROVIDER=minimax|stepfun
    MINIMAX_API_KEY=...  MINIMAX_GROUP_ID=...
    STEPFUN_API_KEY=...
    LLM_BASE_URL=...     (optional override)
    LLM_MODEL=...        (optional override)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class LLMError(RuntimeError):
    """Raised when the model call fails."""


PROVIDERS: dict[str, dict] = {
    "minimax": {
        "base": "https://api.minimax.chat/v1",
        "model": "MiniMax-Text-01",
        "key_env": "MINIMAX_API_KEY",
    },
    "stepfun": {
        "base": "https://api.stepfun.com/v1",
        "model": "step-2-16k",
        "key_env": "STEPFUN_API_KEY",
    },
}


class LLMClient:
    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.provider = (provider or os.environ.get("LLM_PROVIDER") or "minimax").lower()
        cfg = PROVIDERS.get(self.provider, {})
        self.api_key = api_key or os.environ.get(cfg.get("key_env", ""), "")
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or cfg.get("base", "")).rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL") or cfg.get("model", "")
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> str:
        if not self.configured:
            raise LLMError(
                f"LLM not configured for provider={self.provider!r}; "
                "set MINIMAX_API_KEY / STEPFUN_API_KEY in .env"
            )
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        url = f"{self.base_url}/chat/completions"
        group_id = os.environ.get("MINIMAX_GROUP_ID", "")
        if self.provider == "minimax" and group_id:
            url = f"{url}?{urllib.parse.urlencode({'GroupId': group_id})}"

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "ignore")[:400]
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # noqa: BLE001
            raise LLMError(f"request failed: {exc}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise LLMError(f"empty choices in response: {str(data)[:300]}")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):  # some providers return content parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not content:
            raise LLMError(f"empty content in response: {str(data)[:300]}")
        return content
