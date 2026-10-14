"""WebSocket hub. Rooms: show:{id} (public seat updates) and user:{id} (private booking updates).

Single-process in-memory hub. For multiple workers, back `publish` with Redis pub/sub (see README).
"""
import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket

log = logging.getLogger("realtime")


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = defaultdict(set)
        self.loop: asyncio.AbstractEventLoop | None = None

    MAX_PER_ROOM = 2000

    async def join(self, room: str, ws: WebSocket) -> bool:
        if len(self.rooms.get(room, ())) >= self.MAX_PER_ROOM:
            await ws.close(code=1013)  # try again later
            return False
        await ws.accept()
        self.rooms[room].add(ws)
        return True

    def leave(self, room: str, ws: WebSocket) -> None:
        self.rooms[room].discard(ws)
        if not self.rooms[room]:
            self.rooms.pop(room, None)

    async def broadcast(self, room: str, message: dict) -> None:
        for ws in list(self.rooms.get(room, ())):
            try:
                await ws.send_json(message)
            except Exception:
                self.leave(room, ws)

    def publish(self, room: str, message: dict) -> None:
        """Thread-safe: callable from sync endpoints and background threads."""
        if self.loop is None or self.loop.is_closed() or room not in self.rooms:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(room, message), self.loop)
        except Exception:  # never let realtime break a transaction
            log.exception("publish failed")

    def count(self, room: str) -> int:
        return len(self.rooms.get(room, ()))


hub = Hub()


def publish_seats(show_id: int, seats: list[dict]) -> None:
    """seats: [{"id": show_seat_id, "status": "available|locked|booked"}]"""
    if seats:
        hub.publish(f"show:{show_id}", {"type": "seats", "show_id": show_id, "seats": seats})


def publish_user(user_id: int, message: dict) -> None:
    hub.publish(f"user:{user_id}", message)
