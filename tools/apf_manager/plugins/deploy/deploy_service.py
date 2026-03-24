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

Deploy manifests are written to ~/.apf_manager/deployments/ after each deployment:
    <game_id>_framework.json   — files placed by APFrameworkMod
    <game_id>_<folder>.json    — files placed by other AP mods
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

_DEPLOYMENTS_DIR = Path.home() / ".apf_manager" / "deployments"


def _manifest_path(game_id: str, folder_name: str) -> Path:
    key = "framework" if folder_name == "APFrameworkMod" else folder_name
    return _DEPLOYMENTS_DIR / f"{game_id}_{key}.json"

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
        game_id = self._profile.game_id

        with self._lock:
            for mod in mods:
                if mod.is_ap_mod and mod.install_steps:
                    log(f"Deploying {mod.display_name}…")
                    mpath = _manifest_path(game_id, mod.folder_name)
                    engine.run_steps(mod.install_steps, mod, manifest_path=mpath)
            self._mods_txt.save()

    # -----------------------------------------------------------------------
    # Uninstall / manifest API
    # -----------------------------------------------------------------------

    def get_framework_manifest_files(self, game_id: str) -> list[str]:
        """Return the list of files deployed for APFrameworkMod, or [] if no manifest."""
        manifest = _DEPLOYMENTS_DIR / f"{game_id}_framework.json"
        if not manifest.exists():
            return []
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return data.get("files", [])
        except Exception:
            return []

    def uninstall_mod(self, mod_info, game_id: str, log_fn=None) -> None:
        """Remove a deployed mod's files using its manifest, or fallback to uninstall steps."""
        log = log_fn or (lambda msg: None)
        folder_name = mod_info.folder_name
        manifest = _manifest_path(game_id, folder_name)

        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                for f in data.get("files", []):
                    p = Path(f)
                    try:
                        if p.exists():
                            p.unlink()
                            log(f"Removed: {p.name}")
                    except Exception as exc:
                        log(f"[ERR] Could not remove {p.name}: {exc}")
                manifest.unlink(missing_ok=True)
                return
            except Exception as exc:
                log(f"[ERR] Could not read manifest for {folder_name}: {exc} — trying uninstall steps")

        # Fallback: run uninstall steps from install.json
        if not mod_info.uninstall_steps:
            log(f"No uninstall data for {folder_name}")
            return
        with self._lock:
            if not self._profile or not self._detection or not self._mods_txt:
                log(f"Game context unavailable — cannot run uninstall steps for {folder_name}")
                return
            from .install_engine import InstallEngine
            engine = InstallEngine(self._profile, self._detection, self._mods_txt, log_fn=log)
            engine.run_uninstall(mod_info.uninstall_steps, mod_info)

    def reload(self) -> None:
        """Force re-read mods.txt from disk."""
        with self._lock:
            self._reload_mods_txt()