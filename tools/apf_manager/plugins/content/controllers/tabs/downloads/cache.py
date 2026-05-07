"""
CacheController — install / delete logic for cached content items.

Registered as a helper owned by DownloadsTab. No Kivy imports.
X-4: After UE4SS install, calls host.notify_state_change("detection") so the
     pipeline panel re-queries detection state.
"""
from __future__ import annotations

from typing import Callable, Optional


class CacheController:
    """
    Handles all cached-content business logic for the Downloads tab.

    Parameters
    ----------
    host        : plugin host
    on_refresh  : callable() — triggers _scan_cache_and_rebuild() on the view
    """

    def __init__(self, host, on_refresh: Callable) -> None:
        self._host = host
        self._on_refresh = on_refresh

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def validate_and_install(
        self,
        items: list,
        detection,
        game_id: str,
        ue4ss_detected: bool,
        framework_detected: bool,
        on_errors_only: Callable,
        on_warnings: Callable,
        on_proceed: Callable,
    ) -> None:
        """
        Validate items then call one of the three outcome callbacks.

        on_errors_only(errors, warnings) — hard errors; view shows blocking dialog
        on_warnings(errors, warnings, proceed_fn) — soft warnings; view asks user
        on_proceed(sorted_items) — validation passed; view calls do_install()
        """
        other_items = [ci for ci in items if getattr(ci, "category", "mod") == "other"]
        mod_items   = [ci for ci in items if getattr(ci, "category", "mod") != "other"]

        validation_svc = self._host.get_service("validation")
        if validation_svc and detection and mod_items:
            results  = validation_svc.validate_cached(mod_items, detection)
            errors   = [r for r in results if r.status == "error"]
            warnings = [r for r in results if r.status == "warn"]
            if errors:
                on_errors_only(errors, warnings)
                return
            if warnings:
                sorted_items = self.sort_for_install(items, game_id)
                on_warnings(
                    errors, warnings,
                    lambda: on_proceed(sorted_items),
                )
                return

        on_proceed(self.sort_for_install(items, game_id))

    def do_install(
        self,
        items: list,
        detection,
        game_id: str,
        ue4ss_detected: bool,
        framework_detected: bool,
        on_switch_to_installed: Optional[Callable] = None,
    ) -> None:
        """
        Deploy cached items to the game installation.

        After install: rescans mods, re-detects UE4SS if newly installed,
        notifies state changes, then calls on_switch_to_installed if provided.
        X-4: notifies "detection" state change so the pipeline warning bar refreshes.
        """
        deploy_svc = self._host.get_service("deploy")
        if not deploy_svc or not detection:
            return

        ue4ss_was_installed = False

        for ci in list(items):
            try:
                if ci.category == "template":
                    if not (ue4ss_detected and framework_detected):
                        self._host.log(
                            f"[downloads] Skipped template '{ci.display_name}': "
                            "framework mod required"
                        )
                        continue
                elif ci.category == "mod":
                    if not ue4ss_detected:
                        self._host.log(
                            f"[downloads] Skipped mod '{ci.display_name}': UE4SS required"
                        )
                        continue
                deploy_svc.deploy_content(ci.cache_path, ci.content, detection, game_id)
                self._host.log(f"[downloads] Installed {ci.display_name}")

                from ....models.descriptors.types import BinaryDescriptor
                if isinstance(ci.content, BinaryDescriptor) and ci.install_type == "ue4ss":
                    ue4ss_was_installed = True

            except Exception as exc:
                self._host.log(f"[downloads] Install failed for {ci.display_name}: {exc}")

        mods_svc = self._host.get_service("mods")
        if mods_svc:
            mods_svc.rescan()

        if ue4ss_was_installed:
            profile = self._host.get_game_context()
            if profile:
                try:
                    from ......core.controllers.detection import UE4SSDetector
                    new_detection = UE4SSDetector.detect(profile.game_root)
                    self._host.set_game_context(profile, new_detection)
                except Exception as exc:
                    self._host.log(f"[downloads] WARN: re-detect UE4SS failed: {exc}")
            # X-4: Notify pipeline panel so it refreshes the warning bar
            self._host.notify_state_change("detection")

        self._host.notify_state_change("install")

        if on_switch_to_installed:
            on_switch_to_installed()

    def sort_for_install(self, items: list, game_id: str) -> list:
        """Sort cache items in dependency-correct install order."""
        try:
            from ....models.mods.dependency_graph import resolve_install_order
            from ....models.state.pipeline import InstallRecord

            staged = [ci.content for ci in items]
            available: dict = {}
            installed: dict = {}
            registry_svc = self._host.get_service("registry")
            if registry_svc and game_id:
                for m in registry_svc.get_mods(game_id):
                    mid = getattr(m, "mod_id", "")
                    if mid:
                        available[mid] = m
            if game_id:
                from ....models.state.install import InstallStateManager
                installed = {
                    d.get("mod_id", ""): InstallRecord.from_dict(d)
                    for d in InstallStateManager(game_id).get_all()
                    if d.get("mod_id")
                }
            ordered_content, _, _ = resolve_install_order(staged, available, installed)
            content_to_ci = {id(ci.content): ci for ci in items}
            result = [content_to_ci[id(c)] for c in ordered_content if id(c) in content_to_ci]
            seen = {id(ci) for ci in result}
            result += [ci for ci in items if id(ci) not in seen]
            return result
        except Exception as exc:
            self._host.log(f"[cache] WARN: dependency sort failed, using original order: {exc}")
            return items

    def delete(self, ci) -> None:
        """Delete a single cached item from the filesystem and refresh the view."""
        import shutil
        try:
            shutil.rmtree(ci.cache_path, ignore_errors=True)
        except Exception as exc:
            self._host.log(f"[cache] WARN: failed to remove cached item {ci.cache_path}: {exc}")
        self._on_refresh()

    def delete_items(self, items: list) -> None:
        """Delete multiple cached items from the filesystem and refresh the view."""
        import shutil
        for ci in items:
            try:
                shutil.rmtree(ci.cache_path, ignore_errors=True)
            except Exception as exc:
                self._host.log(f"[cache] WARN: failed to remove {ci.cache_path}: {exc}")
        self._on_refresh()
