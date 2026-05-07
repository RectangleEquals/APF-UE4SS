"""
GameHubController — business logic for the game hub screen.

Handles game removal with fresh detection on every invocation (Bug 8B)
and validates all removal paths before any rmtree (Bug 8C).
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...models.config import GameProfile
    from ...models.ue4ss import UE4SSResult
    from ..plugin_host import PluginHost


class GameHubController:
    def __init__(self, host: "PluginHost") -> None:
        self._host = host

    def execute_remove(
        self,
        profile: "GameProfile",
        switch_states: dict,
        after_remove_cb: Callable,
        after_partial_cb: Callable,
    ) -> None:
        """
        Execute game removal in a background thread.

        Gets fresh detection every invocation (Bug 8B — never uses cached detection).
        Validates all removal paths before rmtree (Bug 8C).
        Calls after_remove_cb(errors) if game was removed from library,
        else after_partial_cb(errors).
        """
        detection = self._host.get_detection()  # Bug 8B: always fresh from host
        threading.Thread(
            target=self._run_remove,
            args=(profile, detection, switch_states, after_remove_cb, after_partial_cb),
            daemon=True,
        ).start()

    def _run_remove(
        self,
        profile: "GameProfile",
        detection: Optional["UE4SSResult"],
        switch_states: dict,
        after_remove_cb: Callable,
        after_partial_cb: Callable,
    ) -> None:
        from kivy.clock import Clock
        errors: list[str] = []

        # 1. Remove deployed AP mods
        if switch_states.get("mods"):
            mods_svc = self._host.get_service("mods")
            deploy_svc = self._host.get_service("deploy")
            if mods_svc and deploy_svc:
                try:
                    for mod in mods_svc.scan():
                        if mod.is_ap_mod:
                            deploy_svc.undeploy_mod(mod, detection)
                except Exception as exc:
                    errors.append(str(exc))

        # 2a. Remove deployed session file
        if switch_states.get("deployed_session"):
            if detection and detection.mods_dir:
                state_path = (
                    Path(str(detection.mods_dir))
                    / "APFrameworkMod" / "output" / "session_state.json"
                )
                try:
                    state_path.unlink(missing_ok=True)
                except Exception as exc:
                    errors.append(f"Could not remove deployed session: {exc}")

        # 2b. Remove session history (backups)
        if switch_states.get("sessions"):
            sessions_svc = self._host.get_service("sessions")
            if sessions_svc:
                try:
                    sessions_svc.clear_sessions(profile.game_id)
                except Exception as exc:
                    errors.append(str(exc))

        # 3. Uninstall UE4SS — validate path before rmtree (Bug 8C)
        if switch_states.get("ue4ss"):
            ue4ss_path = detection.ue4ss_dir if detection else None
            if self._validate_removal_path(ue4ss_path, profile):
                try:
                    shutil.rmtree(str(ue4ss_path))
                except Exception as exc:
                    errors.append(f"Could not remove UE4SS: {exc}")
            else:
                errors.append("UE4SS removal skipped: path is None, relative, or outside game root")

        # 4. Remove from library only if that switch is checked
        if switch_states.get("library"):
            if self._host.config:
                self._host.config.remove_game(profile.game_id)
            Clock.schedule_once(lambda dt: after_remove_cb(errors), 0)
        else:
            Clock.schedule_once(lambda dt: after_partial_cb(errors), 0)

    def _validate_removal_path(
        self,
        path: Optional[Path],
        profile: "GameProfile",
    ) -> bool:
        """
        Bug 8C: validate a removal path before any rmtree.

        Checks:
          1. path is not None
          2. path is absolute (rules out Path(".") = CWD)
          3. path is inside profile.game_root
        """
        if path is None:
            return False
        try:
            path = Path(path)
            if not path.is_absolute():
                return False
            game_root = Path(profile.game_root)
            path.relative_to(game_root)  # raises ValueError if not under game_root
            return True
        except (ValueError, TypeError):
            return False
