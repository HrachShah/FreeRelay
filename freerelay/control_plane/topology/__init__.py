"""
FreeRelay Control Plane — Multi-Region Topology & Policy Bus
==============================================================
- Regional topology management
- Policy bus for control plane to data plane communication
- Edge admission control
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import redis.asyncio as aioredis
from pydantic import BaseModel

logger = logging.getLogger("freerelay.control_plane.topology")


class Region(StrEnum):
    US_EAST = "us-east"
    US_WEST = "us-west"
    EU_WEST = "eu-west"
    EU_CENTRAL = "eu-central"
    ASIA_PACIFIC = "asia-pacific"


class NodeRole(StrEnum):
    CONTROL_PLANE = "control_plane"
    DATA_PLANE = "data_plane"
    EDGE = "edge"


class NodeStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"


@dataclass
class RegionalNode:
    node_id: str
    region: Region
    role: NodeRole
    endpoint: str
    status: NodeStatus
    capacity: int
    current_load: int = 0
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(UTC))


class PolicyMessage(BaseModel):
    version: int
    timestamp: datetime
    payload: dict[str, Any]
    source: str
    checksum: str


class PolicyBus:
    """
    Pub/Sub based policy bus for control plane -> data plane communication.
    Topics:
    - freerelay:policy:v2 - routing policy updates
    - freerelay:capability:v2 - capability registry updates
    - freerelay:circuit:v2 - circuit breaker state changes
    """

    POLICY_TOPIC = "freerelay:policy:v2"
    CAPABILITY_TOPIC = "freerelay:capability:v2"
    CIRCUIT_TOPIC = "freerelay:circuit:v2"

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client
        self._pubsub = aioredis.client.PubSub()
        self._handlers: dict[str, list[Callable[[Any], Any]]] = {}

    async def connect(self) -> None:
        """Initialize pub/sub connection."""
        await self._pubsub.subscribe(
            self.POLICY_TOPIC,
            self.CAPABILITY_TOPIC,
            self.CIRCUIT_TOPIC,
        )
        logger.info("Policy bus connected")

    async def publish_policy(self, policy_data: dict[str, Any]) -> str:
        """Publish policy update to all data plane nodes."""
        message = PolicyMessage(
            version=policy_data.get("version", 1),
            timestamp=datetime.now(UTC),
            payload=policy_data,
            source="control_plane",
            checksum=self._compute_checksum(policy_data),
        )

        await self._redis.publish(
            self.POLICY_TOPIC,
            message.model_dump_json(),
        )
        logger.info("Published policy v%d", message.version)
        return message.checksum

    async def publish_capability_update(self, capability_data: dict[str, Any]) -> None:
        """Publish capability registry update."""
        await self._redis.publish(
            self.CAPABILITY_TOPIC,
            json.dumps(capability_data),
        )

    async def publish_circuit_state(self, provider: str, state: dict[str, Any]) -> None:
        """Publish circuit breaker state change."""
        await self._redis.publish(
            self.CIRCUIT_TOPIC,
            json.dumps({"provider": provider, "state": state}),
        )

    def register_handler(self, topic: str, handler: Callable[[Any], Any]) -> None:
        """Register handler for topic messages."""
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)

    async def listen(self) -> None:
        """Listen for messages and dispatch to handlers."""
        async for message in self._pubsub.listen():
            if message["type"] == "message":
                topic = message["channel"]
                if topic in self._handlers:
                    for handler in self._handlers[topic]:
                        try:
                            await handler(message["data"])
                        except Exception:
                            logger.exception("Handler error for %s", topic)

    @staticmethod
    def _compute_checksum(data: dict[str, Any]) -> str:
        """Compute SHA256 checksum of policy payload."""
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[
            :16
        ]

    async def close(self) -> None:
        """Close pub/sub connection."""
        await self._pubsub.close()


class RegionalTopology:
    """
    Manages multi-region topology:
    - Node registration and health monitoring
    - Edge admission control
    - Regional routing preferences
    """

    NODE_TTL = 30  # seconds
    HEALTH_CHECK_INTERVAL = 10

    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client
        self._nodes: dict[str, RegionalNode] = {}
        self._health_tasks: list[asyncio.Task[None]] = []

    async def register_node(self, node: RegionalNode) -> None:
        """Register a new node in the topology."""
        key = f"freerelay:topology:node:{node.node_id}"

        await self._redis.hset(
            key,
            mapping={
                "node_id": node.node_id,
                "region": node.region.value,
                "role": node.role.value,
                "endpoint": node.endpoint,
                "status": node.status.value,
                "capacity": str(node.capacity),
                "last_heartbeat": node.last_heartbeat.isoformat(),
            },
        )
        await self._redis.expire(key, self.NODE_TTL * 2)

        self._nodes[node.node_id] = node
        logger.info("Registered node %s in %s", node.node_id, node.region.value)

    async def heartbeat(self, node_id: str) -> None:
        """Update node heartbeat timestamp."""
        key = f"freerelay:topology:node:{node_id}"
        await self._redis.hset(key, "last_heartbeat", datetime.now(UTC).isoformat())
        await self._redis.expire(key, self.NODE_TTL * 2)

    async def get_nodes_by_region(self, region: Region) -> list[RegionalNode]:
        """Get all healthy nodes in a region."""
        nodes = []
        pattern = "freerelay:topology:node:*"

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            for key in keys:
                data = await self._redis.hgetall(key)
                if (
                    data
                    and data.get(b"region", b"").decode() == region.value
                    and data.get(b"status", b"").decode() == NodeStatus.HEALTHY.value
                ):
                    nodes.append(
                        RegionalNode(
                            node_id=data[b"node_id"].decode(),
                            region=Region(data[b"region"].decode()),
                            role=NodeRole(data[b"role"].decode()),
                            endpoint=data[b"endpoint"].decode(),
                            status=NodeStatus(data[b"status"].decode()),
                            capacity=int(data[b"capacity"].decode()),
                            current_load=int(data.get(b"current_load", b"0").decode()),
                        )
                    )

            if cursor == 0:
                break

        return nodes

    async def get_edge_node(self, region: Region) -> RegionalNode | None:
        """Get the edge node for a region (for admission control)."""
        nodes = await self.get_nodes_by_region(region)
        edges = [n for n in nodes if n.role == NodeRole.EDGE]

        if not edges:
            return None

        # Return the edge with lowest load
        return min(edges, key=lambda n: n.current_load)

    async def update_load(self, node_id: str, load: int) -> None:
        """Update node current load."""
        key = f"freerelay:topology:node:{node_id}"
        await self._redis.hset(key, "current_load", str(load))

    async def get_all_regions(self) -> list[Region]:
        """Get list of all active regions."""
        regions = set()

        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match="freerelay:topology:node:*", count=100
            )
            for key in keys:
                data = await self._redis.hget(key, "region")
                if data:
                    regions.add(Region(data))

            if cursor == 0:
                break

        return list(regions)


class EdgeAdmission:
    """
    Edge admission control:
    - Route requests to nearest healthy edge
    - Enforce per-region rate limits
    - Queue management for traffic spikes
    """

    def __init__(self, topology: RegionalTopology, redis_client: aioredis.Redis):
        self._topology = topology
        self._redis = redis_client

    async def admit(self, namespace: str, region: Region) -> tuple[bool, str | None]:
        """
        Attempt to admit request at edge.
        Returns (admitted, edge_endpoint).
        """
        edge = await self._topology.get_edge_node(region)

        if edge is None:
            return False, None

        # Check rate limit
        key = f"freerelay:ratelimit:edge:{region.value}:{namespace}"
        current = await self._redis.get(key)

        if current and int(current) >= edge.capacity:
            return False, None

        return True, edge.endpoint

    async def record_request(self, namespace: str, region: Region) -> None:
        """Record request for rate limiting."""
        key = f"freerelay:ratelimit:edge:{region.value}:{namespace}"
        await self._redis.incr(key)
        await self._redis.expire(key, 60)  # 1 minute window
