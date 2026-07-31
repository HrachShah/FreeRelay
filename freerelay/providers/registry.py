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
        # Map each module_name -> set of provider names that module registered.
        # This lets reload_plugins() look up the actual provider keys (not file
        # paths) so _providers.pop() removes the right entries.
        self._loaded_modules: dict[str, set[str]] = {}

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

            registered_names: set[str] = set()
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
                            registered_names.add(attr.name)  # type: ignore[attr-defined]
                            loaded += 1
                            logger.info(
                                "Loaded plugin provider: %s from %s",
                                attr.name,  # type: ignore[attr-defined]
                                py_file.name,
                            )

                    self._loaded_modules[module_name] = registered_names

            except ImportError as e:
                logger.error("Failed to load plugin %s: %s", py_file.name, e)
            except (SyntaxError, AttributeError) as e:
                # SyntaxError: the plugin file itself failed to compile
                # AttributeError: BaseProvider subclass is missing required attrs
                # Both indicate a broken plugin and should be surfaced loudly
                # rather than silently logged as a generic "Exception"
                logger.error("Invalid plugin %s: %s", py_file.name, e)

        return loaded

    def reload_plugins(self) -> int:
        """
        Reload all plugins from the plugin directory.

        Returns:
            Number of providers after reload.
        """
        # Remove previously loaded plugin modules.
        # Look up provider names by module_name (not by file path) so
        # _providers.pop() actually removes the right entries.
        for module_name, provider_names in list(self._loaded_modules.items()):
            sys.modules.pop(module_name, None)
            for provider_name in provider_names:
                self._providers.pop(provider_name, None)
        self._loaded_modules.clear()

        # Re-discover
        self.discover_plugins()
        return len(self._providers)
