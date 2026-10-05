from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from vibe.core.types import LLMMessage
from vibe.utils import AgentEntrypoint
from vibe.utils.terminal import TerminalEmulator


class AttachmentKind(StrEnum):
    IMAGE = "image"


class LaunchContext(BaseModel):
    """Local client metadata carried to llama.cpp requests and logs only."""

    agent_entrypoint: AgentEntrypoint
    agent_version: str
    client_name: str
    client_version: str
    terminal_emulator: TerminalEmulator | None = None


CallType = Literal["main_call", "secondary_call"]


class RequestMetadata(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    session_id: str | None = None
    parent_session_id: str | None = None
    call_type: CallType
    call_source: str = "vibe_local"
    host_kind: Literal["local"] = "local"
    message_id: str | None = None


def build_launch_context(
    *,
    agent_entrypoint: AgentEntrypoint,
    agent_version: str,
    client_name: str,
    client_version: str,
    terminal_emulator: TerminalEmulator | None = None,
) -> LaunchContext:
    return LaunchContext(
        agent_entrypoint=agent_entrypoint,
        agent_version=agent_version,
        client_name=client_name,
        client_version=client_version,
        terminal_emulator=terminal_emulator,
    )


def build_request_metadata(
    *,
    launch_context: LaunchContext | None,
    session_id: str | None,
    parent_session_id: str | None = None,
    call_type: CallType,
    message_id: str | None = None,
) -> RequestMetadata:
    del launch_context
    return RequestMetadata(
        session_id=session_id,
        parent_session_id=parent_session_id,
        call_type=call_type,
        message_id=message_id,
    )


def build_attachment_counts(
    message: LLMMessage | None, *, supports_images: bool
) -> dict[AttachmentKind, int]:
    if message is None or not supports_images or not message.images:
        return {}
    return {AttachmentKind.IMAGE: len(message.images)}
