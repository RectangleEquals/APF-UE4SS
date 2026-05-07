"""
AppController — plugin lifecycle, navigation logic, and app-level orchestration.

Owns PluginHost and APFConfig. The view (APFManagerApp) delegates all
business logic here and receives callbacks for UI-specific responses.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.config import APFConfig, GameProfile
    from .plugin_host import PluginHost


def _builtin_plugins_dir() -> Path:
    """
    Returns the built-in plugins directory.
    In development: tools/apf_manager/plugins/ (relative to this file).
    In frozen build: plugins/ (relative to executable).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "plugins"
    else:
        # core/controllers/app.py → core/controllers/ → core/ → apf_manager/ → plugins/
        return Path(__file__).parent.parent.parent / "plugins"


def _custom_plugins_dir() -> Path:
    """User-installed plugins: next to the executable (frozen) or ~/.apf_manager/plugins/."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "custom_plugins"
    return Path.home() / ".apf_manager" / "plugins"


class AppController:
    def __init__(self, devtools_mode: bool = False) -> None:
        from ..models.config import APFConfig
        from .plugin_host import PluginHost

        self._devtools_mode = devtools_mode
        self._config = APFConfig()
        self._host = PluginHost()
        self._host.set_config(self._config)

    @property
    def host(self) -> "PluginHost":
        return self._host

    @property
    def config(self) -> "APFConfig":
        return self._config

    def startup(
        self,
        navigate_fn: Callable,
        dialog_fn: Callable,
        failure_fn: Callable,
        log_fn: Optional[Callable] = None,
    ) -> None:
        """Load config and plugins; wire host callbacks."""
        self._config.load()
        self._host.discover_and_load(
            plugin_dirs=[_builtin_plugins_dir(), _custom_plugins_dir()],
            disabled_ids=self._config.disabled_plugins,
            dev_mode=self._config.is_dev,
            devtools_mode=self._devtools_mode,
        )
        self._host.set_navigate_fn(navigate_fn)
        self._host.set_dialog_fn(dialog_fn)
        self._host.set_failure_fn(failure_fn)
        if log_fn:
            self._host.set_log_fn(log_fn)

    def navigate_to_game(self, profile: "GameProfile") -> None:
        """Run UE4SS detection and update host game context. View handles UI navigation."""
        from .detection import UE4SSDetector
        detection = UE4SSDetector.detect(profile.game_root)
        self._host.set_game_context(profile, detection)
        self._config.last_game_id = profile.game_id
        self._config.save()
