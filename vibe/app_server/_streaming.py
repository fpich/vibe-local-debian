from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import suppress

_EVENT_QUEUE_MAX_SIZE = 64


class BoundedEventQueue[EventT](asyncio.Queue[EventT]):
    def __init__(self) -> None:
        super().__init__(maxsize=_EVENT_QUEUE_MAX_SIZE)


def finish_event_queue[EventT](
    events: asyncio.Queue[EventT], terminal_event: EventT
) -> None:
    while not events.empty():
        events.get_nowait()
    events.put_nowait(terminal_event)


async def stream_until_complete[EventT, ResultT](
    events: asyncio.Queue[EventT],
    completion: asyncio.Task[ResultT],
    *,
    event_task_name: str | None = None,
) -> AsyncGenerator[EventT, None]:
    pending_event: asyncio.Task[EventT] | None = None
    try:
        while not completion.done():
            pending_event = asyncio.create_task(events.get(), name=event_task_name)
            done, _ = await asyncio.wait(
                (completion, pending_event), return_when=asyncio.FIRST_COMPLETED
            )
            if pending_event in done:
                yield pending_event.result()
                pending_event = None
                continue
            pending_event.cancel()
            with suppress(asyncio.CancelledError):
                await pending_event
            pending_event = None

        while not events.empty():
            yield events.get_nowait()
    finally:
        if pending_event is not None and not pending_event.done():
            pending_event.cancel()
            with suppress(asyncio.CancelledError):
                await pending_event
