from __future__ import annotations

import json

from vibe.core.config.models import ProviderConfig
from vibe.core.llm.backend.generic import _get_adapter
from vibe.core.types import LLMMessage, Role


def _make_provider(**overrides: object) -> ProviderConfig:
    defaults: dict[str, object] = {
        "name": "llamacpp-worker1",
        "api_base": "http://127.0.0.1:8080/v1",
        "api_key_env_var": "",
        "api_style": "openai",
    }
    defaults.update(overrides)
    return ProviderConfig(**defaults)  # type: ignore[arg-type]


def _prepare_payload(provider: ProviderConfig) -> dict:
    adapter = _get_adapter(provider.api_style)
    req = adapter.prepare_request(
        model_name="worker1",
        messages=[LLMMessage(role=Role.user, content="hello")],
        temperature=0.2,
        tools=None,
        max_tokens=None,
        tool_choice=None,
        enable_streaming=False,
        provider=provider,
    )
    return json.loads(req.body)


def test_generic_adapter_requests_prompt_caching_by_default() -> None:
    payload = _prepare_payload(_make_provider())
    assert payload["cache_prompt"] is True


def test_generic_adapter_omits_cache_prompt_when_disabled() -> None:
    payload = _prepare_payload(_make_provider(cache_prompt=False))
    assert "cache_prompt" not in payload
