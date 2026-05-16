"""
FreeRelay — Provider Registry (§5)
=====================================
Plugin discovery and hot reload for providers.
Supports loading providers from a plugin directory.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

from freerelay.providers.base import BaseProvider

logger = logging.getLogger("freerelay.registry")


class ProviderRegistry:
    """
    Dynamic provider registry with plugin discovery.

    Can load provider classes from Python files in a plugin directory
    and supports hot reloading when files change.
    """

    def __init__(self, plugin_dir: Path | None = None) -> None:
        self.plugin_dir = plugin_dir or Path.home() / ".freerelay" / "plugins"
        self._providers: dict[str, type[BaseProvider]] = {}
        self._loaded_modules: dict[str, str] = {}

    def register(self, provider_cls: type[BaseProvider]) -> None:
        """Register a provider class."""
        self._providers[provider_cls.name] = provider_cls  # type: ignore[attr-defined]
        logger.debug("Registered provider class: %s", provider_cls.name)  # type: ignore[attr-defined]

    def get(self, name: str) -> type[BaseProvider] | None:
        """Get a provider class by name."""
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def discover_plugins(self) -> int:
        """
        Discover and load provider plugins from the plugin directory.

        Returns:
            Number of newly loaded plugins.
        """
        if not self.plugin_dir.exists():
            logger.info("Plugin directory does not exist: %s", self.plugin_dir)
            return 0

        loaded = 0
        for py_file in self.plugin_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue

            module_name = f"freerelay.plugins.{py_file.stem}"
            if module_name in self._loaded_modules:
                continue

            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    # Look for BaseProvider subclasses
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseProvider)
                            and attr is not BaseProvider
                        ):
                            self.register(attr)
                            loaded += 1
                            logger.info(
                                "Loaded plugin provider: %s from %s",
                                attr.name,
                                py_file.name,
                            )

                    self._loaded_modules[module_name] = str(py_file)

            except (ImportError, SyntaxError, AttributeError) as e:
                logger.error("Failed to load plugin %s: %s", py_file.name, e)

        return loaded

    def reload_plugins(self) -> int:
        """
        Reload all plugins from the plugin directory.

        Returns:
            Number of providers after reload.
        """
        # Remove previously loaded plugin modules
        for module_name in list(self._loaded_modules.keys()):
            sys.modules.pop(module_name, None)
            # Also remove plugin-registered providers
            provider_name = self._loaded_modules[module_name]
            self._providers.pop(provider_name, None)
        self._loaded_modules.clear()

        # Re-discover
        self.discover_plugins()
        return len(self._providers)
