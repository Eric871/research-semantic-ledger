"""Minimal OpenAI-compatible provider client used by the online extraction tier."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol, Sequence


DEFAULT_DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


class ProviderError(RuntimeError):
    """A terminal provider or response-contract failure."""


@dataclass(frozen=True)
class ProviderResponse:
    payload: dict[str, Any]
    raw_response: dict[str, Any]
    usage: dict[str, int]
    observed_model: str | None
    finish_reason: str | None


class JsonProvider(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        max_output_tokens: int,
    ) -> ProviderResponse: ...


def _response_json_object(raw: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    choices = raw.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ProviderError("provider_response_choices_invalid")
    choice = choices[0]
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("provider_response_content_empty")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"provider_response_json_invalid:{exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("provider_response_json_root_must_be_object")
    finish_reason = choice.get("finish_reason")
    return parsed, finish_reason if isinstance(finish_reason, str) else None


class DeepSeekProvider:
    """Dependency-free DeepSeek chat-completions adapter.

    The API key is read once from the environment and is never returned in a
    receipt. There is deliberately no automatic retry.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 180,
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ProviderError("DEEPSEEK_API_KEY_not_set")
        self.endpoint = endpoint or os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_ENDPOINT
        self.model = model or os.environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL
        self.timeout_seconds = timeout_seconds
        if not self.endpoint.startswith("https://"):
            raise ProviderError("provider_endpoint_must_use_https")

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        max_output_tokens: int,
    ) -> ProviderResponse:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False, separators=(",", ":")),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": max_output_tokens,
            "stream": False,
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_bytes = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", errors="replace")
            raise ProviderError(f"provider_http_error:{exc.code}:{detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"provider_transport_error:{type(exc).__name__}:{exc}") from exc
        try:
            raw = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderError(f"provider_envelope_invalid:{type(exc).__name__}") from exc
        if not isinstance(raw, dict):
            raise ProviderError("provider_envelope_root_must_be_object")
        payload, finish_reason = _response_json_object(raw)
        if finish_reason not in {None, "stop"}:
            raise ProviderError(f"provider_finish_reason:{finish_reason}")
        usage_raw = raw.get("usage")
        usage = {
            "prompt_tokens": int((usage_raw or {}).get("prompt_tokens") or 0),
            "completion_tokens": int((usage_raw or {}).get("completion_tokens") or 0),
            "total_tokens": int((usage_raw or {}).get("total_tokens") or 0),
        }
        observed_model = raw.get("model")
        return ProviderResponse(
            payload=payload,
            raw_response=raw,
            usage=usage,
            observed_model=observed_model if isinstance(observed_model, str) else None,
            finish_reason=finish_reason,
        )


class SequenceProvider:
    """Deterministic in-memory provider used by tests and offline examples."""

    def __init__(self, payloads: Sequence[dict[str, Any]]) -> None:
        self._payloads = list(payloads)
        self.calls = 0

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        max_output_tokens: int,
    ) -> ProviderResponse:
        del system_prompt, user_payload, max_output_tokens
        if not self._payloads:
            raise ProviderError("sequence_provider_exhausted")
        payload = self._payloads.pop(0)
        self.calls += 1
        return ProviderResponse(
            payload=payload,
            raw_response={"fixture": True, "payload": payload},
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            observed_model="sequence-provider",
            finish_reason="stop",
        )
