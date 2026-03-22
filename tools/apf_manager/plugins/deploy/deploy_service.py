"""
DeployService — public service API for the deploy plugin.

Registered as the "deploy" service so other plugins (e.g. future mod-sets plugin)
can call:
    svc = host.get_service("deploy")
    svc.set_enabled("MyMod", True)
    svc.reorder(["APFrameworkMod", "MyMod", "OtherMod"])
    svc.deploy_all()

Also owns the shared ModsTextManager instance so both the panel and external
callers share the same in-memory state.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.ue4ss import UE4SSResult
    from ..mods.mod_service import ModService
    from .mods_txt import ModsTextManager


class DeployService:
    def __init__(self, host) -> None:
        self._host = host
        self._mods_txt: Optional["ModsTextManager"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._profile: Optional["GameProfile"] = None
        self._lock = threading.Lock()

    # Called by PluginHost when game context changes
    def on_game_changed(self, profile: Optional["GameProfile"], detection: Optional["UE4SSResult"]) -> None:
        with self._lock:
            self._profile = profile
            self._detection = detection
            self._reload_mods_txt()

    def _reload_mods_txt(self) -> None:
        if self._detection and self._detection.mods_txt:
            from .mods_txt import ModsTextManager
            self._mods_txt = ModsTextManager(self._detection.mods_txt)
            self._mods_txt.load()
        else:
            self._mods_txt = None

    # -----------------------------------------------------------------------
    # Public API (inter-plugin)
    # -----------------------------------------------------------------------

    @property
    def mods_txt(self) -> Optional["ModsTextManager"]:
        return self._mods_txt

    def get_load_order(self) -> list[str]:
        with self._lock:
            return self._mods_txt.get_order() if self._mods_txt else []

    def set_enabled(self, folder_name: str, enabled: bool) -> None:
        with self._lock:
            if self._mods_txt:
                self._mods_txt.set_enabled(folder_name, enabled)
                self._mods_txt.save()

    def ensure_entry(self, folder_name: str, enabled: bool = True) -> None:
        with self._lock:
            if self._mods_txt:
                self._mods_txt.ensure_entry(folder_name, enabled)
                self._mods_txt.save()

    def reorder(self, order: list[str]) -> None:
        with self._lock:
            if self._mods_txt:
                self._mods_txt.reorder(order)
                self._mods_txt.save()

    def deploy_all(self, log_fn=None) -> None:
        """Run install steps for all AP mods. Blocking — call from a thread."""
        if not self._profile or not self._detection or not self._mods_txt:
            return

        log = log_fn or (lambda msg: None)
        mods_svc: Optional["ModService"] = self._host.get_service("mods")
        if not mods_svc:
            log("mods service unavailable — deploy skipped.")
            return

        from .install_engine import InstallEngine
        engine = InstallEngine(self._profile, self._detection, self._mods_txt, log_fn=log)
        mods = mods_svc.scan()

        with self._lock:
            for mod in mods:
                if mod.is_ap_mod and mod.install_steps:
                    log(f"Deploying {mod.display_name}…")
                    engine.run_steps(mod.install_steps, mod)
            self._mods_txt.save()

    def reload(self) -> None:
        """Force re-read mods.txt from disk."""
        with self._lock:
            self._reload_mods_txt()