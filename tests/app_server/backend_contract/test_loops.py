from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import time

import httpx
import pytest
import respx

from tests.app_server.backend_contract.conftest import (
    BackendContractConnection,
    connect_backend_contract_host,
)
from vibe.app_server.protocol import (
    AppServerResponseError,
    ClientCapabilities,
    ProtocolErrorCode,
    SessionOptions,
)
from vibe.app_server.session import AppServerSession


@pytest.mark.asyncio
async def test_loop_resource_supports_crud(
    backend_contract_session: AppServerSession,
) -> None:
    """*Prepare*: An attached session with no scheduled loops.
    *Do*: Create, list, delete, and clear loops through the public resource.
    *Assert*: Every mutation returns the typed loop state shared by both backends.
    """
    # Prepare
    assert await backend_contract_session.resources.loops.list() == []

    # Do
    first = await backend_contract_session.resources.loops.create("30s", "first")
    second = await backend_contract_session.resources.loops.create("1m", "second")
    listed = await backend_contract_session.resources.loops.list()
    deleted = await backend_contract_session.resources.loops.delete(first.id)
    cleared = await backend_contract_session.resources.loops.clear()

    # Assert
    assert listed == [first, second]
    assert deleted == first
    assert cleared == 1
    assert await backend_contract_session.resources.loops.list() == []


@pytest.mark.asyncio
async def test_loop_resource_returns_typed_validation_errors(
    backend_contract_session: AppServerSession,
) -> None:
    """*Prepare*: An attached session accepting loop resource requests.
    *Do*: Create a loop with an invalid interval.
    *Assert*: Both backends return the public invalid-params error.
    """
    # Prepare / Do
    with pytest.raises(AppServerResponseError) as exc_info:
        await backend_contract_session.resources.loops.create("invalid", "prompt")

    # Assert
    assert exc_info.value.error.code is ProtocolErrorCode.INVALID_PARAMS
    assert "Invalid interval" in exc_info.value.error.message


@pytest.mark.asyncio
async def test_loop_schedule_survives_resume_from_a_new_host(
    backend_contract_mistral_api: respx.Route,
    backend_contract_mistral_response: Callable[[str], httpx.Response],
    backend_contract_persistent_connection: BackendContractConnection,
) -> None:
    """*Prepare*: A persisted session with one scheduled loop, then a fresh backend Host.
    *Do*: Resume the session and list its loops.
    *Assert*: The same schedule is restored for both session implementations.
    """
    # Prepare
    backend_contract_mistral_api.mock(
        return_value=backend_contract_mistral_response("stored")
    )
    session = await backend_contract_persistent_connection.host.open_session()
    loop = await session.resources.loops.create("30s", "persist me")
    _ = [event async for event in session.act("persist the session")]
    session_id = session.session_id
    await session.close()
    resumed_connection = await connect_backend_contract_host(
        session_options=SessionOptions(), capabilities=ClientCapabilities()
    )

    # Do
    resumed = await resumed_connection.host.resume_session(session_id)
    try:
        restored = await resumed.resources.loops.list()
    finally:
        await resumed.close()

    # Assert
    assert restored == [loop]


@pytest.mark.asyncio
async def test_clear_history_preserves_loop_schedules(
    backend_contract_persistent_session: AppServerSession,
) -> None:
    """*Prepare*: A session with one scheduled loop.
    *Do*: Clear its history.
    *Assert*: The replacement session preserves the loop schedule.
    """
    # Prepare
    loop = await backend_contract_persistent_session.resources.loops.create(
        "30s", "keep me"
    )

    # Do
    await backend_contract_persistent_session.clear_history()
    after_clear = await backend_contract_persistent_session.resources.loops.list()

    # Assert
    assert after_clear == [loop]


def _mark_unified_loop_due(tmp_path: Path, session_id: str) -> Path:
    path = tmp_path / "sessions" / "unified" / session_id / "scheduled-loops.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["loops"][0]["next_fire_at"] = time.time() - 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
