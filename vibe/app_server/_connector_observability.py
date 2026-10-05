"""No-op connector observability for the local-only build.

Connector catalogs are disabled at runtime, but a small compatibility surface remains
until the protocol/config types are removed in the architecture simplification pass.
"""

from __future__ import annotations

from typing import Literal

type ConnectorCatalogOperation = Literal[
    "authorization", "bootstrap", "cache_write", "convergence"
]
type ConnectorCatalogOutcome = Literal[
    "busy",
    "cancelled",
    "deduplicated",
    "failure",
    "invalid",
    "rejected",
    "stale",
    "success",
    "unavailable",
]
type ConnectorCacheDisposition = Literal["memory", "fresh_cache", "not_loaded"]


def record_connector_catalog_operation(
    _elapsed_s: float,
    *,
    operation: ConnectorCatalogOperation,
    outcome: ConnectorCatalogOutcome,
    backend: Literal["legacy", "unified"],
) -> None:
    del operation, outcome, backend


def add_connector_cache_read(
    *, disposition: ConnectorCacheDisposition, backend: Literal["legacy", "unified"]
) -> None:
    del disposition, backend


__all__ = ["add_connector_cache_read", "record_connector_catalog_operation"]
