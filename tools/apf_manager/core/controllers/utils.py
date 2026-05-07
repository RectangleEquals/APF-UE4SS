"""core/controllers/utils.py — plugin asset path resolver."""

from pathlib import Path


def get_plugin_root(plugin_file) -> Path:
    """Walk up from any file inside a plugin until plugin.json is found."""
    path = Path(plugin_file).resolve().parent
    while path != path.parent:
        if (path / "plugin.json").exists():
            return path
        path = path.parent
    raise FileNotFoundError(f"plugin.json not found above {plugin_file}")


def get_plugin_asset(plugin_file, *parts: str) -> Path:
    """Resolve an asset path relative to the plugin's root directory.

    Works in both dev and cx_Freeze deployed builds — plugins/ is copied as
    real files, so plugin.json is always findable at runtime.

    Usage:
        _SPA_PATH = get_plugin_asset(__file__, "assets", "registry", "viewer_spa.html")
    """
    return get_plugin_root(plugin_file).joinpath(*parts)
