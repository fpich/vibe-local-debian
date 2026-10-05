from __future__ import annotations

from typing import TYPE_CHECKING, Any

from vibe.core.config import ProviderConfig
from vibe.core.config._defaults import (
    DEFAULT_API_CONNECT_TIMEOUT,
    DEFAULT_API_POOL_TIMEOUT,
    DEFAULT_API_RETRY_MAX_ELAPSED_TIME,
    DEFAULT_API_TIMEOUT,
    DEFAULT_API_WRITE_TIMEOUT,
)
from vibe.core.types import Backend

if TYPE_CHECKING:
    from collections.abc import Callable

    from vibe.core.llm.types import BackendLike
    from vibe.core.utils import RetryObserver


def _create_generic_backend(**kwargs: Any) -> BackendLike:
    from vibe.core.llm.backend.generic import GenericBackend

    return GenericBackend(**kwargs)


# The factories import the backend modules on first use rather than at module
# level: the backends pull in heavy dependencies that would otherwise slow CLI
# startup.
BACKEND_FACTORY: dict[Backend, Callable[..., BackendLike]] = {
    Backend.GENERIC: _create_generic_backend,
}


def create_backend(
    *,
    provider: ProviderConfig,
    timeout: float = DEFAULT_API_TIMEOUT,
    retry_max_elapsed_time: float = DEFAULT_API_RETRY_MAX_ELAPSED_TIME,
    connect_timeout: float = DEFAULT_API_CONNECT_TIMEOUT,
    write_timeout: float = DEFAULT_API_WRITE_TIMEOUT,
    pool_timeout: float = DEFAULT_API_POOL_TIMEOUT,
    enable_otel: bool = False,
    on_retry: RetryObserver | None = None,
) -> BackendLike:
    backend = Backend(provider.backend)
    if backend is not Backend.GENERIC:
        raise ValueError(
            f"Backend {backend.value!r} is not supported by the local-only build"
        )
    factory = BACKEND_FACTORY[backend]
    return factory(
        provider=provider,
        timeout=timeout,
        retry_max_elapsed_time=retry_max_elapsed_time,
        enable_otel=False,
        on_retry=on_retry,
    )
