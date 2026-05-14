"""
RegistriesController — all registry service interactions for Tab 1.

Fix A: provides on_viewer_requested callback wrapped in Clock.schedule_once so
       the registry service never imports Kivy or launches the viewer directly.
"""
from __future__ import annotations

from typing import Callable, Optional


class RegistriesController:
    """Non-Kivy controller for RegistriesTab."""

    def __init__(self, host) -> None:
        self._host = host

    # -----------------------------------------------------------------------
    # Registry CRUD
    # -----------------------------------------------------------------------

    def get_user_registries(self, game_id: str) -> list:
        svc = self._svc()
        return svc.get_user_registries(game_id) if svc else []

    def add_registry(
        self,
        url: str,
        game_id: str,
        on_done: Callable,
    ) -> None:
        """Add a registry URL; shows the RegistryViewer if the repo has multiple folders."""
        svc = self._svc()
        if not svc:
            return

        # Fix A: supply viewer callback so the service never imports Kivy
        def _on_viewer_requested(kwargs: dict) -> None:
            from kivy.clock import Clock
            from ...registry.viewer import RegistryViewer

            def _ui(dt):
                RegistryViewer(self._host).show(**kwargs)

            Clock.schedule_once(_ui, 0)

        svc.add_registry_with_viewer(
            url, game_id,
            on_done=on_done,
            on_viewer_requested=_on_viewer_requested,
        )

    def remove_registry(self, url: str) -> None:
        svc = self._svc()
        if svc:
            svc.remove_registry(url)

    def refresh_all(self, on_done: Callable) -> None:
        svc = self._svc()
        if svc:
            svc.refresh_all(on_done=on_done)

    # -----------------------------------------------------------------------
    # Search + share
    # -----------------------------------------------------------------------

    def search_github(self, game_id: str, on_done: Callable) -> None:
        svc = self._svc()
        if svc:
            svc.search_github(game_id, on_done=on_done)

    def export_registries_b64(self) -> str:
        svc = self._svc()
        return svc.export_registries_b64() if svc else ""

    def import_registries_b64(self, encoded: str) -> list:
        svc = self._svc()
        return svc.import_registries_b64(encoded) if svc else []

    def is_share_payload(self, url: str) -> bool:
        svc = self._svc()
        return bool(svc and svc.is_share_payload(url))

    def is_blacklisted(self, owner: str, repo: str) -> bool:
        svc = self._svc()
        if not svc:
            return False
        resolver = svc._get_resolver() if hasattr(svc, "_get_resolver") else None
        return bool(resolver and resolver.is_blacklisted(owner, repo))

    # -----------------------------------------------------------------------
    # Rate limit callbacks
    # -----------------------------------------------------------------------

    def set_rate_limit_callbacks(
        self,
        on_rate_limit: Callable,
        on_search_rate_limit: Callable,
    ) -> None:
        svc = self._svc()
        if svc and hasattr(svc, "set_rate_limit_callbacks"):
            svc.set_rate_limit_callbacks(
                on_rate_limit=on_rate_limit,
                on_search_rate_limit=on_search_rate_limit,
            )

    # -----------------------------------------------------------------------
    # UE4SS update info (for UE4SS status card)
    # -----------------------------------------------------------------------

    def get_ue4ss_update_info(self):
        if self._host.has_service("updates"):
            return self._host.get_service("updates").get_update_info("ue4ss")
        return None

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _svc(self):
        if self._host.has_service("registry"):
            return self._host.get_service("registry")
        return None
