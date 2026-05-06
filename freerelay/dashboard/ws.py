"""
FreeRelay — WebSocket Live Metrics (§5)
==========================================
Real-time metrics push via WebSocket for the dashboard.
Broadcasts provider stats, request rates, and system health.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

logger = logging.getLogger("freerelay.dashboard_ws")


class MetricsBroadcaster:
    """
    WebSocket metrics broadcaster.

    Periodically pushes metrics to connected WebSocket clients.
    Used by the dashboard for real-time updates.
    """

    def __init__(self, interval: float = 2.0) -> None:
        self.interval = interval
        self._clients: list[Any] = []
        self._task: asyncio.Task[None] | None = None

    async def connect(self, websocket: Any) -> None:
        """Register a WebSocket client."""
        await websocket.accept()
        self._clients.append(websocket)

    def disconnect(self, websocket: Any) -> None:
        """Unregister a WebSocket client."""
        if websocket in self._clients:
            self._clients.remove(websocket)

    async def broadcast(self, data: dict[str, object]) -> None:
        """Send data to all connected clients."""
        message = json.dumps(data)
        disconnected: list[Any] = []

        for client in self._clients:
            try:
                await client.send_text(message)
            except (RuntimeError, AttributeError):
                disconnected.append(client)

        for client in disconnected:
            self._clients.remove(client)

    async def start_broadcasting(self, get_metrics: Any) -> None:
        """
        Start periodic metrics broadcasting.

        Args:
            get_metrics: Async callable that returns metrics dict.
        """
        while True:
            try:
                if self._clients:
                    metrics = (
                        await get_metrics()
                        if asyncio.iscoroutinefunction(get_metrics)
                        else get_metrics()
                    )
                    await self.broadcast(
                        {
                            "type": "metrics",
                            "timestamp": int(time.time()),
                            "data": metrics,
                        }
                    )
            except (RuntimeError, OSError) as e:
                logger.error("Metrics broadcast error: %s", e)

            await asyncio.sleep(self.interval)

    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self._clients)
