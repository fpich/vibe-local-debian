from __future__ import annotations

import copy
from typing import Any

from vibe.core.config.fingerprint import create_dict_fingerprint
from vibe.core.config.layer import ConfigLayer, RawConfig
from vibe.core.config.types import LayerConfigSnapshot
from vibe.observability.logging import logger

# Fields an agent profile must never override because they may route credentials.
PROTECTED_FIELDS = frozenset({
})


class AgentProfileLayer(ConfigLayer[RawConfig]):
    """In-memory layer holding the currently active agent profile overrides."""

    NAME = "agent-profile"

    def __init__(self, *, data: dict[str, Any] | None = None, name: str = NAME) -> None:
        super().__init__(name=name)
        self._data = self._strip_protected(copy.deepcopy(data or {}))

    @staticmethod
    def _strip_protected(data: dict[str, Any]) -> dict[str, Any]:
        if blocked := PROTECTED_FIELDS.intersection(data):
            logger.warning(
                "Ignoring protected field(s) %s in agent profile overrides",
                ", ".join(sorted(blocked)),
            )
            for field in blocked:
                del data[field]
        return data

    async def _check_trust(self) -> bool:
        return True

    async def _build_config_snapshot(self) -> LayerConfigSnapshot:
        data = copy.deepcopy(self._data)
        fingerprint = create_dict_fingerprint(data)
        return LayerConfigSnapshot(data=data, fingerprint=fingerprint)

    async def _save_to_store(self, next_config: RawConfig) -> str:
        self._data = self._strip_protected(copy.deepcopy(next_config.model_dump()))
        return create_dict_fingerprint(self._data)
