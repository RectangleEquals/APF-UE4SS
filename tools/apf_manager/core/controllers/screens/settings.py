"""
SettingsController — business logic for the settings screen.

Handles mode toggle, plugin enable/disable, cache clearing, app restart,
and Steam path save. All shutil/subprocess/os operations live here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...models.config import APFConfig
    from ..plugin_host import PluginHost


class SettingsController:
    def __init__(self, host: "PluginHost", config: "APFConfig") -> None:
        self._host = host
        self._config = config

    def toggle_mode(self, dev_mode: bool) -> None:
        self._config.mode = "dev" if dev_mode else "player"
        self._config.save()

    def toggle_plugin(self, plugin_id: str, enabled: bool) -> bool:
        """
        Enable or disable a plugin. Returns False if the operation was blocked
        (sole home_screen provider cannot be disabled).
        """
        if not enabled:
            home_contribs = self._host.get_contributions("home_screen")
            if home_contribs and all(c.plugin_id == plugin_id for c in home_contribs):
                return False  # blocked
        self._config.set_plugin_disabled(plugin_id, not enabled)
        return True

    def save_steam_override(self, value: str) -> None:
        self._config.steam_library_override = value.strip() or None
        self._config.save()

    def clear_download_cache(self) -> str:
        """Clear all download sub-directories from ~/.apf_manager/cache/. Returns status message."""
        import shutil
        cache_dir = Path.home() / ".apf_manager" / "cache"
        try:
            if cache_dir.is_dir():
                for child in cache_dir.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    else:
                        child.unlink(missing_ok=True)
            return "Download cache cleared."
        except Exception as exc:
            return f"Error clearing cache: {exc}"

    def notify_downloads_stale(self) -> None:
        """Mark the Downloads tab cache as stale so it re-scans on next activation."""
        try:
            for contrib in self._host.get_contributions("hub_panel"):
                panel = getattr(contrib, "panel_instance", None)
                if panel and hasattr(panel, "mark_downloads_stale"):
                    panel.mark_downloads_stale()
                    break
        except Exception:
            pass

    def schedule_reset_app_data(self) -> str:
        """Write the pending-reset marker. Returns status message."""
        app_data_dir = Path.home() / ".apf_manager"
        marker = app_data_dir / "_pending_reset"
        try:
            app_data_dir.mkdir(parents=True, exist_ok=True)
            marker.write_text("1", encoding="utf-8")
            return ""
        except Exception as exc:
            return f"Error scheduling reset: {exc}"

    def restart_app(self, stop_fn: Optional[Callable] = None) -> None:
        """Restart the application. Calls stop_fn() before launching subprocess if provided."""
        if getattr(sys, "frozen", False):
            os.execv(sys.executable, [sys.executable])
        else:
            import subprocess
            # core/controllers/screens/settings.py → core/controllers/screens/ → core/controllers/
            # → core/ → apf_manager/
            tools_dir = Path(__file__).parent.parent.parent.parent
            subprocess.Popen([sys.executable, "-m", "apf_manager"], cwd=str(tools_dir))
            if stop_fn:
                stop_fn()
