"""
Klinik — Redis Streams Event Bus
Real-time agent event broadcasting for the live dashboard.
Each agent publishes status events as it runs, and the frontend
subscribes via Server-Sent Events (SSE) to get live updates.
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, AsyncGenerator
import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

STREAM_KEY = "klinik:agent-events"
MAX_STREAM_LENGTH = 1000


class EventBus:
    """Redis Streams based event bus for real-time agent status updates."""

    def __init__(self):
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        settings = get_settings()
        try:
            self._redis = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("📡 Redis event bus connected")
        except Exception as e:
            logger.warning(f"Redis not available — events will be in-memory only: {e}")
            self._redis = None

    async def disconnect(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()

    async def publish_agent_event(
        self,
        session_id: str,
        agent_name: str,
        status: str,
        output: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """
        Publish an agent status change event to Redis Streams.
        The frontend subscribes to these events for live dashboard updates.
        """
        event = {
            "session_id": session_id,
            "agent_name": agent_name,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if output:
            event["output"] = output[:500]  # Truncate for stream efficiency
        if error:
            event["error"] = error[:200]

        if self._redis:
            try:
                await self._redis.xadd(
                    f"{STREAM_KEY}:{session_id}",
                    event,
                    maxlen=MAX_STREAM_LENGTH,
                )
            except Exception as e:
                logger.error(f"Failed to publish event: {e}")
        else:
            # Fallback: just log
            logger.info(f"📡 Event: {agent_name} → {status}")

    async def subscribe_session_events(
        self, session_id: str, last_id: str = "0"
    ) -> AsyncGenerator[dict, None]:
        """
        Subscribe to agent events for a specific session.
        Yields events as they arrive — used for SSE endpoint.
        """
        stream_key = f"{STREAM_KEY}:{session_id}"

        if not self._redis:
            return

        while True:
            try:
                results = await self._redis.xread(
                    {stream_key: last_id},
                    count=10,
                    block=5000,  # 5 second block
                )

                if results:
                    for stream_name, messages in results:
                        for msg_id, msg_data in messages:
                            last_id = msg_id
                            yield msg_data

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stream read error: {e}")
                await asyncio.sleep(1)

    async def get_session_events(self, session_id: str) -> list[dict]:
        """Get all events for a session (for initial dashboard load)."""
        stream_key = f"{STREAM_KEY}:{session_id}"

        if not self._redis:
            return []

        try:
            results = await self._redis.xrange(stream_key)
            return [data for _, data in results]
        except Exception as e:
            logger.error(f"Failed to read events: {e}")
            return []


# ── Singleton ──
_event_bus: Optional[EventBus] = None


async def get_event_bus() -> EventBus:
    """Get or create the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
        await _event_bus.connect()
    return _event_bus
