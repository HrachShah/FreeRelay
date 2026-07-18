from pathlib import Path

from freerelay.providers.registry import ProviderRegistry


def write_plugin(path: Path, provider_name: str) -> None:
    path.write_text(
        f"""from freerelay.providers.base import BaseProvider

class PluginProvider(BaseProvider):
    name = {provider_name!r}
    base_url = "https://example.com"
    supported_features = set()

    async def complete(self, request, api_key):
        return None

    async def stream(self, request, api_key):
        if False:
            yield ""

    def estimate_tokens(self, request):
        return 0
"""
    )


def test_reload_removes_providers_from_previous_plugin_version(tmp_path):
    plugin = tmp_path / "example.py"
    write_plugin(plugin, "first")
    registry = ProviderRegistry(tmp_path)

    assert registry.discover_plugins() == 1
    assert registry.get("first") is not None

    write_plugin(plugin, "second")
    assert registry.reload_plugins() == 1
    assert registry.get("first") is None
    assert registry.get("second") is not None
