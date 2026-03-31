"""
FreeRelay — Multi-Tenant Namespace Isolation
================================================
Provides namespace-based isolation for multi-tenant deployments.
Each namespace has its own rate limits, provider keys, and audit trail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger("freerelay.tenancy")


@dataclass
class Namespace:
    """A tenant namespace with isolated configuration."""

    name: str
    display_name: str = ""
    api_key_hash: str = ""
    rate_limit_rpm: int = 60
    enabled: bool = True
    allowed_providers: list[str] = field(default_factory=list)  # empty = all
    metadata: dict[str, str] = field(default_factory=dict)


class NamespaceManager:
    """
    Manages tenant namespaces for multi-tenant isolation.

    In production, namespaces are stored in Redis or a database.
    For now, uses in-memory storage.
    """

    def __init__(self) -> None:
        self._namespaces: dict[str, Namespace] = {}
        # Default namespace
        self._namespaces["default"] = Namespace(
            name="default",
            display_name="Default",
            enabled=True,
        )

    def get_namespace(self, name: str) -> Namespace | None:
        """Get a namespace by name."""
        return self._namespaces.get(name)

    def create_namespace(self, namespace: Namespace) -> None:
        """Create a new namespace."""
        self._namespaces[namespace.name] = namespace
        logger.info("Created namespace: %s", namespace.name)

    def delete_namespace(self, name: str) -> bool:
        """Delete a namespace. Cannot delete 'default'."""
        if name == "default":
            return False
        if name in self._namespaces:
            del self._namespaces[name]
            return True
        return False

    def list_namespaces(self) -> list[Namespace]:
        """List all namespaces."""
        return list(self._namespaces.values())

    def resolve_namespace(self, api_key_hash: str) -> str:
        """
        Resolve a namespace from an API key hash.

        Returns:
            Namespace name, or 'default' if not found.
        """
        for ns in self._namespaces.values():
            if ns.api_key_hash == api_key_hash:
                return ns.name
        return "default"
