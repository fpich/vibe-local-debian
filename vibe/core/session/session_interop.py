from __future__ import annotations

from dataclasses import dataclass

from vibe.core.config import SessionLoggingConfig
from vibe.core.session.session_loader import SessionLoader
from vibe.utils.session_id import shorten_session_id


class InvalidLegacyInteropSourceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LegacySessionReference:
    session_id: str
    cwd: str
    root_session_id: str
    parent_session_id: str | None


def resolve_legacy_session_reference(
    session_id: str, config: SessionLoggingConfig
) -> LegacySessionReference | None:
    sessions = SessionLoader.list_sessions(config)
    exact = [session for session in sessions if session["session_id"] == session_id]
    matches = exact or [
        session
        for session in sessions
        if shorten_session_id(session["session_id"]) == session_id
    ]
    if not matches:
        return None
    canonical_ids = {session["session_id"] for session in matches}
    if len(canonical_ids) != 1:
        raise InvalidLegacyInteropSourceError(
            f"Legacy session ID is ambiguous: {session_id}"
        )
    selected = matches[0]
    parents = {
        session["session_id"]: session["parent_session_id"] for session in sessions
    }
    canonical_id = selected["session_id"]
    return LegacySessionReference(
        session_id=canonical_id,
        cwd=selected["cwd"],
        root_session_id=_root_session_id(canonical_id, parents),
        parent_session_id=selected["parent_session_id"],
    )


def _root_session_id(session_id: str, parents: dict[str, str | None]) -> str:
    seen: set[str] = set()
    current = session_id
    while (parent := parents.get(current)) is not None and parent in parents:
        if parent in seen:
            return session_id
        seen.add(current)
        current = parent
    return current
