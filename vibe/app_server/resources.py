from __future__ import annotations

from vibe.app_server._runtime_resources import (
    AgentResource,
    ConfigResource,
    RuntimeResource,
)
from vibe.app_server._session_resources import (
    LoopsResource,
    ReviewResource,
    SessionResource,
    ShellResource,
    WorkspaceResource,
)
from vibe.app_server.client_state import ClientSessionState
from vibe.app_server.connection import AppServerResourceConnection
from vibe.app_server.events import AppServerEvent
from vibe.app_server.protocol import Notification

__all__ = ["AppServerResources"]


class AppServerResources:
    """Client resources used by the local Textual frontend.

    Cloud account/identity, MCP/connectors, plugin catalog and registry-skill
    resources were intentionally removed from the local-only product surface.
    """

    def __init__(
        self, connection: AppServerResourceConnection, state: ClientSessionState
    ) -> None:
        self.config = ConfigResource(connection, state)
        self.agents = AgentResource(connection, state)
        self.runtime = RuntimeResource(connection, state)
        self.shell = ShellResource(connection, state)
        self.sessions = SessionResource(connection, state)
        self.review = ReviewResource(connection, state)
        self.workspace = WorkspaceResource(connection, state)
        self.loops = LoopsResource(connection, state)

    async def refresh(self) -> None:
        await self.runtime.refresh()

    async def consume_notification(self, notification: Notification) -> bool:
        previous_config = self.config.current
        if await self.runtime.consume_notification(notification):
            self.config.publish_change(previous_config)
            return True
        return False

    async def consume_event(self, event: AppServerEvent) -> bool:
        return await self.shell.consume_event(event)
