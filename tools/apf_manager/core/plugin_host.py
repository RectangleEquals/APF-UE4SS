"""
PluginHost — plugin lifecycle, contribution registry, and inter-plugin service registry.

Plugins are Python packages containing:
  - plugin.json  (metadata: id, name, version, mode, requires, suggests, contributions)
  - __init__.py  (exports: def setup(host: PluginHost) -> None)

Contribution types: home_screen, hub_panel, hub_action, dialog, settings_panel
Service registry: plugins can register named services for other plugins to consume.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, TYPE_CHECKING

# The apf_manager package root (tools/apf_manager/).
# Used to detect whether a plugin is a built-in (inside the package)
# or a user plugin (outside, standalone).
_APF_PKG_ROOT = Path(__file__).parent.parent
_APF_PKG_NAME = __name__.split(".")[0]  # e.g. "apf_manager"

if TYPE_CHECKING:
    from .config import GameProfile
    from .ue4ss import UE4SSResult


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class PluginContribution:
    type: str                           # "home_screen" | "hub_panel" | "hub_action" | "dialog" | "settings_panel"
    plugin_id: str
    label: str = ""
    icon: str = ""
    priority: int = 50                  # Lower = earlier in nav rail
    panel_class: Any = None             # Widget class for hub_panel / home_screen
    handler: Optional[Callable] = None  # For hub_action / dialog
    dialog_id: str = ""                 # For dialog contributions


@dataclass
class PluginInfo:
    plugin_id: str
    name: str
    version: str
    description: str
    mode: str                           # "player" | "dev" | "both"
    requires: list = field(default_factory=list)
    suggests: list = field(default_factory=list)
    contributions: list = field(default_factory=list)  # raw dicts from plugin.json
    directory: Path = field(default_factory=Path)
    status: str = "pending"            # "pending" | "loaded" | "failed"
    error: str = ""                    # Human-readable failure reason (if status == "failed")


# ---------------------------------------------------------------------------
# PluginHost
# ---------------------------------------------------------------------------

class PluginHost:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginInfo] = {}
        self._contributions: list[PluginContribution] = []
        self._services: dict[str, Any] = {}
        self._game_context: Optional["GameProfile"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._log_fn: Optional[Callable[[str], None]] = None
        self._navigate_fn: Optional[Callable[["GameProfile"], None]] = None
        self._dialog_fn: Optional[Callable[[str, dict], None]] = None
        self._failure_fn: Optional[Callable[[], None]] = None
        self.has_failures: bool = False

    # -----------------------------------------------------------------------
    # Plugin discovery & loading
    # -----------------------------------------------------------------------

    def discover_and_load(self, plugin_dirs: list[Path], disabled_ids: list[str], dev_mode: bool) -> None:
        """
        Discover all plugins in the given directories, resolve dependencies,
        and load them in topological order.
        """
        raw: list[PluginInfo] = []

        for d in plugin_dirs:
            if not d.is_dir():
                continue
            for plugin_dir in sorted(d.iterdir()):
                if not plugin_dir.is_dir():
                    continue
                manifest_path = plugin_dir / "plugin.json"
                # Support both plugin_dir/plugin.json and plugin_dir/<pkg>/plugin.json
                if not manifest_path.exists():
                    # Check one level deeper (for packages where __init__ is in sub-folder)
                    candidates = list(plugin_dir.glob("*/plugin.json"))
                    if candidates:
                        manifest_path = candidates[0]
                    else:
                        continue
                try:
                    meta = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    continue

                info = PluginInfo(
                    plugin_id=meta.get("id", ""),
                    name=meta.get("name", plugin_dir.name),
                    version=meta.get("version", "0.0.0"),
                    description=meta.get("description", ""),
                    mode=meta.get("mode", "both"),
                    requires=meta.get("requires", []),
                    suggests=meta.get("suggests", []),
                    contributions=meta.get("contributions", []),
                    directory=plugin_dir,
                    status="pending",
                )

                if not info.plugin_id:
                    continue
                if info.plugin_id in disabled_ids:
                    info.status = "failed"
                    info.error = "Disabled by user."
                    self._plugins[info.plugin_id] = info
                    continue

                # Filter by mode
                if info.mode == "dev" and not dev_mode:
                    # Skip silently — not a failure, just not applicable
                    continue

                raw.append(info)
                self._plugins[info.plugin_id] = info

        # Resolve load order + detect circular deps
        ordered = self._topological_sort(raw)

        for info in ordered:
            self._load_plugin(info)

        self.has_failures = any(
            p.status == "failed" and p.error != "Disabled by user."
            for p in self._plugins.values()
        )

    def _topological_sort(self, plugins: list[PluginInfo]) -> list[PluginInfo]:
        """Sort plugins by requires/suggests dependencies. Marks circular deps as failed."""
        id_to_info = {p.plugin_id: p for p in plugins}
        visited: set[str] = set()
        in_stack: set[str] = set()
        order: list[PluginInfo] = []

        def visit(pid: str, path: list[str]) -> None:
            if pid in in_stack:
                # Circular dependency — mark all in cycle as failed
                cycle_start = path.index(pid)
                cycle = path[cycle_start:]
                msg = " → ".join(cycle) + f" → {pid}"
                for cid in cycle:
                    if cid in id_to_info:
                        info = id_to_info[cid]
                        info.status = "failed"
                        # Find display names for clear messaging
                        names = [id_to_info[c].name if c in id_to_info else c for c in cycle]
                        if len(names) == 2:
                            info.error = (
                                f"'{names[0]}' and '{names[1]}' each require the other "
                                f"and cannot both load. Disable one in Settings."
                            )
                        else:
                            info.error = (
                                f"Circular dependency detected: {msg}. "
                                f"Disable one of the affected plugins in Settings."
                            )
                return
            if pid in visited:
                return
            in_stack.add(pid)
            info = id_to_info.get(pid)
            if info:
                for dep_id in info.requires + info.suggests:
                    if dep_id in id_to_info:
                        visit(dep_id, path + [pid])
            in_stack.discard(pid)
            visited.add(pid)
            if info:
                order.append(info)

        for p in plugins:
            if p.plugin_id not in visited:
                visit(p.plugin_id, [])

        return order

    def _load_plugin(self, info: PluginInfo) -> None:
        """Import the plugin package and call setup(host)."""
        if info.status == "failed":
            return

        # Verify hard dependencies are loaded successfully
        for dep_id in info.requires:
            dep = self._plugins.get(dep_id)
            if dep is None or dep.status != "loaded":
                dep_name = dep.name if dep else dep_id
                info.status = "failed"
                info.error = (
                    f"'{info.name}' needs '{dep_name}' to run. "
                    f"Enable it in Settings."
                )
                return

        try:
            module = self._import_plugin(info)
            if hasattr(module, "setup"):
                module.setup(self)
            info.status = "loaded"
        except Exception as exc:
            info.status = "failed"
            # Brief, actionable message — show exception type but not full traceback
            info.error = (
                f"'{info.name}' failed to load: {type(exc).__name__}: {exc}. "
                f"Contact the plugin author."
            )

    # -----------------------------------------------------------------------
    # Plugin import helper
    # -----------------------------------------------------------------------

    @staticmethod
    def _import_plugin(info: PluginInfo):
        """
        Import a plugin package, preserving relative-import compatibility.

        Built-in plugins live inside the apf_manager package (tools/apf_manager/plugins/).
        They use relative imports (from ...core import ...) and must be imported
        with their full dotted module name (e.g. "apf_manager.plugins.diagnostics").

        User plugins live outside the package and are imported standalone by
        adding their parent directory to sys.path.
        """
        plugin_dir = info.directory

        try:
            rel = plugin_dir.relative_to(_APF_PKG_ROOT)
            # Built-in: compute full dotted name, e.g. "apf_manager.plugins.diagnostics"
            full_name = _APF_PKG_NAME + "." + ".".join(rel.parts)
            # Ensure the package root's parent (tools/) is importable
            pkg_root_parent = str(_APF_PKG_ROOT.parent)
            if pkg_root_parent not in sys.path:
                sys.path.insert(0, pkg_root_parent)
            return importlib.import_module(full_name)
        except ValueError:
            # User plugin — standalone package
            plugin_parent = str(plugin_dir.parent)
            if plugin_parent not in sys.path:
                sys.path.insert(0, plugin_parent)
            return importlib.import_module(plugin_dir.name)

    # -----------------------------------------------------------------------
    # Contribution registration (called by plugins during setup)
    # -----------------------------------------------------------------------

    def register_contribution(self, plugin_id: str, contribution: PluginContribution) -> None:
        contribution.plugin_id = plugin_id
        self._contributions.append(contribution)

    def get_contributions(self, type: str) -> list[PluginContribution]:
        result = [c for c in self._contributions if c.type == type]
        result.sort(key=lambda c: c.priority)
        return result

    # -----------------------------------------------------------------------
    # Service registry
    # -----------------------------------------------------------------------

    def register_service(self, service_id: str, service: Any) -> None:
        self._services[service_id] = service

    def get_service(self, service_id: str) -> Any:
        return self._services.get(service_id)

    def has_service(self, service_id: str) -> bool:
        return service_id in self._services

    # -----------------------------------------------------------------------
    # Game context
    # -----------------------------------------------------------------------

    def get_game_context(self) -> Optional["GameProfile"]:
        return self._game_context

    def get_detection(self) -> Optional["UE4SSResult"]:
        return self._detection

    def set_game_context(self, profile: Optional["GameProfile"], detection: Optional["UE4SSResult"] = None) -> None:
        self._game_context = profile
        self._detection = detection
        # Notify all services that have an on_game_changed callback.
        # mods service receives (profile); others receive (profile, detection).
        for svc_id, svc in self._services.items():
            if not hasattr(svc, "on_game_changed"):
                continue
            try:
                if svc_id == "mods":
                    svc.on_game_changed(profile)
                else:
                    svc.on_game_changed(profile, detection)
            except Exception:
                pass

    def navigate_to_game(self, profile: "GameProfile") -> None:
        if self._navigate_fn:
            self._navigate_fn(profile)

    def get_all_plugins(self) -> list["PluginInfo"]:
        """Return all discovered plugins (loaded and failed) sorted by name."""
        return sorted(self._plugins.values(), key=lambda p: p.name.lower())

    # -----------------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------------

    def show_dialog(self, dialog_id: str, **kwargs) -> None:
        if self._dialog_fn:
            self._dialog_fn(dialog_id, kwargs)

    def log(self, msg: str) -> None:
        if self._log_fn:
            self._log_fn(msg)

    # -----------------------------------------------------------------------
    # Wiring (set by the GUI app after construction)
    # -----------------------------------------------------------------------

    def set_log_fn(self, fn: Callable[[str], None]) -> None:
        self._log_fn = fn

    def set_navigate_fn(self, fn: Callable) -> None:
        self._navigate_fn = fn

    def set_dialog_fn(self, fn: Callable) -> None:
        self._dialog_fn = fn

    def set_failure_fn(self, fn: Callable[[], None]) -> None:
        self._failure_fn = fn

    def report_failure(self, plugin_id: str, error: str) -> None:
        """Called by a plugin at runtime to report a critical failure."""
        if plugin_id in self._plugins:
            self._plugins[plugin_id].status = "failed"
            self._plugins[plugin_id].error = error
        self.has_failures = True
        if self._failure_fn:
            self._failure_fn()

    # -----------------------------------------------------------------------
    # Introspection
    # -----------------------------------------------------------------------

    def get_all_plugins(self) -> list[PluginInfo]:
        return list(self._plugins.values())

    def get_failed_plugins(self) -> list[PluginInfo]:
        return [p for p in self._plugins.values() if p.status == "failed"]
