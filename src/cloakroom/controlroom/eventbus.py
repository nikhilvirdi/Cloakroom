"""Event bus for publishing gateway events to Control Room and audit log."""

import asyncio
import contextlib
import sqlite3
from collections import deque
from pathlib import Path
from typing import Final

from cloakroom.contracts import GatewayEvent
from cloakroom.errors import GatewayError

_MAX_HISTORY: Final = 1000  # Rolling in-memory history limit


class EventBus:
    """Event bus with asyncio.Queue fan-out, rolling history, and SQLite audit log."""

    def __init__(self, *, audit_db_path: Path | None = None) -> None:
        """Initialize event bus.

        Args:
            audit_db_path: Path to SQLite audit log (None to skip persistence)
        """
        self._subscribers: list[asyncio.Queue[GatewayEvent]] = []
        self._history: deque[GatewayEvent] = deque(maxlen=_MAX_HISTORY)
        self._audit_db_path = audit_db_path
        self._lock = asyncio.Lock()

        if audit_db_path:
            self._init_audit_db()

    def _init_audit_db(self) -> None:
        """Initialize SQLite audit log schema."""
        if not self._audit_db_path:
            return

        try:
            self._audit_db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(self._audit_db_path)) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_events (
                        event_id TEXT PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        tool_id TEXT,
                        effect TEXT,
                        cloud_view TEXT,
                        entity_count INTEGER,
                        latency_ms REAL,
                        tripwire_passed INTEGER,
                        decision TEXT
                    )
                    """
                )
                conn.commit()
        except (sqlite3.Error, OSError) as e:
            raise GatewayError() from e

    async def publish(self, event: GatewayEvent) -> None:
        """Publish event to all subscribers, add to history, and persist to audit log.

        Args:
            event: Gateway event to publish
        """
        async with self._lock:
            # Add to rolling history
            self._history.append(event)

            # Fan out to subscribers
            for queue in self._subscribers:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

            # Persist to audit log
            if self._audit_db_path:
                self._persist_to_audit(event)

    def _persist_to_audit(self, event: GatewayEvent) -> None:
        """Persist event to SQLite audit log (cloud view only)."""
        try:
            with sqlite3.connect(str(self._audit_db_path)) as conn:
                conn.execute(
                    """
                    INSERT INTO audit_events (
                        event_id, event_type, timestamp, tool_id, effect,
                        cloud_view, entity_count, latency_ms, tripwire_passed, decision
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.event_type,
                        event.timestamp.isoformat(),
                        event.tool_id,
                        event.effect.value if event.effect else None,
                        str(event.cloud_view) if event.cloud_view else None,
                        len(event.entities),
                        event.latency_ms,
                        1 if event.tripwire_passed else 0,
                        event.decision,
                    ),
                )
                conn.commit()
        except sqlite3.Error:
            # Fail open for audit logging - don't block gateway operations
            pass

    def subscribe(self) -> asyncio.Queue[GatewayEvent]:
        """Subscribe to events. Returns a queue that will receive all future events.

        Returns:
            Queue that receives GatewayEvent objects
        """
        queue: asyncio.Queue[GatewayEvent] = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[GatewayEvent]) -> None:
        """Unsubscribe from events.

        Args:
            queue: Queue to remove from subscribers
        """
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    def get_history(self) -> list[GatewayEvent]:
        """Get rolling event history (up to last 1000 events).

        Returns:
            List of recent events, oldest first
        """
        return list(self._history)
