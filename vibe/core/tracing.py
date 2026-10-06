from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

type Span = Any


def build_otel_span_exporter_config(*_args: Any, **_kwargs: Any) -> None:
    """Tracing is disabled in the local-only build."""
    return None


def setup_tracing(*_args: Any, **_kwargs: Any) -> None:
    """Tracing is disabled in the local-only build."""


@asynccontextmanager
async def agent_span(**_kwargs: Any) -> AsyncGenerator[None]:
    yield None


@asynccontextmanager
async def tool_span(**_kwargs: Any) -> AsyncGenerator[None]:
    yield None


@asynccontextmanager
async def model_call_span(**_kwargs: Any) -> AsyncGenerator[None]:
    yield None


@asynccontextmanager
async def hook_span(**_kwargs: Any) -> AsyncGenerator[None]:
    yield None


def set_model_call_http_status(_span: Any, _status_code: int) -> None:
    return None


def set_model_call_usage(
    _span: Any, *, prompt_tokens: int, completion_tokens: int
) -> None:
    return None


def set_model_call_response_metadata(
    _span: Any, _response_data: dict[str, Any]
) -> None:
    return None


def set_tool_result(_span: Any, _result: str) -> None:
    return None
