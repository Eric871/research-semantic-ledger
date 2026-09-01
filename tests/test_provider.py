from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_semantic_ledger.provider import (
    DeepSeekProvider,
    ProviderError,
    ReplayThenProvider,
    SequenceProvider,
)


class _FakeHttpResponse:
    def __init__(self, content: str = '{"status":"ok"}') -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": self.content},
                    }
                ],
                "model": "deepseek-v4-flash",
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 2,
                    "total_tokens": 12,
                },
            }
        ).encode("utf-8")


class DeepSeekProviderTests(unittest.TestCase):
    def test_exact_successful_request_is_replayed_with_zero_billable_usage(self) -> None:
        raw_response = json.loads(_FakeHttpResponse().read().decode("utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            raw_dir = Path(directory) / "raw"
            raw_dir.mkdir()
            (raw_dir / "call-0001.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "request": {"system_prompt": "system", "user_payload": {"input": "fixture"}},
                        "response": raw_response,
                    }
                ),
                encoding="utf-8",
            )
            provider = ReplayThenProvider(SequenceProvider([]), [Path(directory)])
            response = provider.complete_json(
                system_prompt="system",
                user_payload={"input": "fixture"},
                max_output_tokens=100,
            )

        self.assertTrue(response.replayed)
        self.assertEqual(response.usage["total_tokens"], 0)
        self.assertEqual(response.replay_original_usage["total_tokens"], 12)

    def test_chat_request_explicitly_disables_thinking(self) -> None:
        provider = DeepSeekProvider(api_key="test-key")
        captured: dict[str, object] = {}

        def fake_urlopen(request, timeout):
            del timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return _FakeHttpResponse()

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            response = provider.complete_json(
                system_prompt="Return one JSON object.",
                user_payload={"input": "fixture"},
                max_output_tokens=100,
            )

        self.assertEqual(captured["body"]["thinking"], {"type": "disabled"})
        self.assertEqual(response.payload, {"status": "ok"})
        self.assertEqual(response.usage["total_tokens"], 12)

    def test_invalid_json_error_preserves_provider_envelope(self) -> None:
        provider = DeepSeekProvider(api_key="test-key")

        with patch("urllib.request.urlopen", return_value=_FakeHttpResponse("{invalid}")):
            with self.assertRaises(ProviderError) as caught:
                provider.complete_json(
                    system_prompt="Return one JSON object.",
                    user_payload={"input": "fixture"},
                    max_output_tokens=100,
                )

        self.assertEqual(str(caught.exception), "provider_response_json_invalid:Expecting property name enclosed in double quotes")
        self.assertIsInstance(caught.exception.raw_response, dict)
        self.assertEqual(caught.exception.raw_response["usage"]["total_tokens"], 12)


if __name__ == "__main__":
    unittest.main()
