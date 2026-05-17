"""
GameHubController — business logic for the game hub screen.

Handles game removal with fresh detection on every invocation (Bug 8B)
and validates all removal paths before any rmtree (Bug 8C).

AD-4c+d: All uninstall paths use InstallRecord-based tracked removal via
undeploy_content(), never live-scan undeploy_mod(). Only tracked content
is removed; manually-placed files are not touched.
"""

from __future__ import annotations

import logging
import shutil
import threading
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

logger = logging.getLogger(__name__)

_FALLBACK_MOD_NAME = "APFrameworkMod"

if TYPE_CHECKING:
    from ...models.config import GameProfile
    from ...models.ue.result import DetectionResult
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
        detection: Optional["DetectionResult"],
        switch_states: dict,
        after_remove_cb: Callable,
        after_partial_cb: Callable,
    ) -> None:
        from kivy.clock import Clock
        errors: list[str] = []

        deploy_svc = self._host.get_service("deploy")

        # 1. Remove deployed mods (AP mods + non-AP mods + framework mod).
        # Uses tracked InstallRecord entries only — manually-placed mods are not touched.
        if switch_states.get("mods"):
            try:
                records = self._get_tracked_records(profile.game_id)
                mod_types = {"ap_mod", "third_party_mod", "framework_mod"}
                mod_records = [r for r in records if r.content_type in mod_types]
                # Remove dependents before their dependencies to avoid broken intermediate states.
                for record in _sorted_for_removal(mod_records):
                    if deploy_svc:
                        try:
                            deploy_svc.undeploy_content(record, detection)
                            logger.info(f"[game_hub] Removed tracked mod: {record.name!r}")
                        except Exception as exc:
                            msg = f"Failed to remove '{record.name}': {exc}"
                            logger.error(f"[game_hub] {msg}")
                            errors.append(msg)
                    else:
                        logger.warning(
                            f"[game_hub] deploy_svc unavailable; skipped: {record.name!r}"
                        )
            except Exception as exc:
                msg = f"Mod removal failed: {exc}"
                logger.error(f"[game_hub] {msg}")
                errors.append(msg)

        # 2a. Remove deployed session file
        if switch_states.get("deployed_session"):
            if detection and detection.ue4ss and detection.ue4ss.mods_dir:
                if detection.framework_mod:
                    mod_dir = detection.framework_mod.mod_dir
                else:
                    mod_dir = detection.ue4ss.mods_dir / _FALLBACK_MOD_NAME
                state_path = mod_dir / "output" / "session_state.json"
                try:
                    state_path.unlink(missing_ok=True)
                    logger.info(f"[game_hub] Removed session file: {state_path}")
                except Exception as exc:
                    msg = f"Could not remove deployed session: {exc}"
                    logger.error(f"[game_hub] {msg}")
                    errors.append(msg)

        # 2b. Remove session history (backups)
        if switch_states.get("sessions"):
            sessions_svc = self._host.get_service("sessions")
            if sessions_svc:
                try:
                    sessions_svc.clear_sessions(profile.game_id)
                    logger.info(f"[game_hub] Cleared session history for {profile.game_id}")
                except Exception as exc:
                    msg = str(exc)
                    logger.error(f"[game_hub] Session history clear failed: {msg}")
                    errors.append(msg)

        # 3. Uninstall binary content (UE4SS, AP Framework binaries).
        # Uses tracked InstallRecord entries via undeploy_content() → _undeploy_binary_record().
        # Falls back to the validated rmtree path if no tracked binary record exists.
        if switch_states.get("ue4ss"):
            binary_removed = False
            try:
                records = self._get_tracked_records(profile.game_id)
                binary_types = {"github_release_binary", "external_url_binary", "manual_binary"}
                binary_records = [r for r in records if r.content_type in binary_types]
                if binary_records and deploy_svc:
                    for record in binary_records:
                        try:
                            deploy_svc.undeploy_content(record, detection)
                            logger.info(
                                f"[game_hub] Removed tracked binary: {record.name!r}"
                            )
                            binary_removed = True
                        except Exception as exc:
                            msg = f"Failed to remove binary '{record.name}': {exc}"
                            logger.error(f"[game_hub] {msg}")
                            errors.append(msg)
            except Exception as exc:
                msg = f"Binary record lookup failed: {exc}"
                logger.error(f"[game_hub] {msg}")
                errors.append(msg)

            # Fallback (Bug 8C): validate-and-rmtree if no tracked record removed the ue4ss dir.
            ue4ss_dir = (
                detection.ue4ss.ue4ss_dir if (detection and detection.ue4ss) else None
            )
            if not binary_removed and ue4ss_dir and ue4ss_dir.exists():
                if self._validate_removal_path(ue4ss_dir, profile):
                    try:
                        shutil.rmtree(str(ue4ss_dir))
                        logger.info(f"[game_hub] Removed UE4SS (fallback rmtree): {ue4ss_dir}")
                    except Exception as exc:
                        msg = f"Could not remove UE4SS: {exc}"
                        logger.error(f"[game_hub] {msg}")
                        errors.append(msg)
                else:
                    msg = "UE4SS removal skipped: path is None, relative, or outside game root"
                    logger.warning(f"[game_hub] {msg}")
                    errors.append(msg)

        # AD-4e: refresh detection so all tabs (esp. LibraryScreen) see the updated disk state.
        try:
            self._host.refresh_detection()
            logger.info("[game_hub] Detection refreshed after removal")
        except Exception as exc:
            logger.warning(f"[game_hub] Post-removal detection refresh failed: {exc}")

        # 4. Remove from library only if that switch is checked
        if switch_states.get("library"):
            if self._host.config:
                self._host.config.remove_game(profile.game_id)
            Clock.schedule_once(lambda dt: after_remove_cb(errors), 0)
        else:
            Clock.schedule_once(lambda dt: after_partial_cb(errors), 0)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _get_tracked_records(self, game_id: str) -> list:
        """Return all InstallRecord entries tracked for game_id."""
        if not game_id:
            return []
        try:
            from ....plugins.content.models.state.install import InstallStateManager
            from ....plugins.content.models.state.pipeline import InstallRecord
            return [
                InstallRecord.from_dict(d)
                for d in InstallStateManager(game_id).get_all()
            ]
        except Exception as exc:
            logger.warning(f"[game_hub] Could not load install records for {game_id!r}: {exc}")
            return []

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


def _sorted_for_removal(records: list) -> list:
    """
    Sort InstallRecord list so dependents are removed before their dependencies.

    Mods that many others depend on (e.g. APFrameworkMod) are placed last.
    Records without a mod_id are appended at the end.
    """
    mod_records = [r for r in records if r.mod_id]
    no_mod_id = [r for r in records if not r.mod_id]

    # Count how many other mods in this batch depend on each mod.
    dependent_count: dict[str, int] = {r.mod_id: 0 for r in mod_records}
    for r in mod_records:
        for dep_id in (r.dependencies or []):
            if dep_id in dependent_count:
                dependent_count[dep_id] += 1

    # Ascending sort: mods with fewer dependents (leaf nodes) first.
    sorted_mods = sorted(mod_records, key=lambda r: dependent_count.get(r.mod_id, 0))
    return sorted_mods + no_mod_id
