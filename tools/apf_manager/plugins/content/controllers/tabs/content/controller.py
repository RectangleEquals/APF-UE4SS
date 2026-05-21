"""
ContentController — registry queries, validation, and queue state for Tab 2.

Handles all service interactions so ContentTab view never imports services directly.
"""
from __future__ import annotations

from typing import Callable, Optional, Tuple

from ......core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)


class ContentController:
    """Non-Kivy controller for ContentTab."""

    def __init__(self, host) -> None:
        self._host = host

    # -----------------------------------------------------------------------
    # Registry content retrieval
    # -----------------------------------------------------------------------

    def get_mods(self, game_id: str) -> list:
        svc = self._registry_svc()
        return (svc.get_mods(game_id) or []) if svc else []

    def get_templates(self, game_id: str) -> list:
        svc = self._registry_svc()
        return (svc.get_templates(game_id) or []) if svc else []

    def get_other_content(self, game_id: str) -> list:
        """Synchronous fetch of UE4SS / framework binary items from registry."""
        svc = self._registry_svc()
        if svc and hasattr(svc, "get_other_content"):
            return svc.get_other_content(game_id) or []
        return []

    def get_ue4ss_releases_for_content(self, owner: str, repo: str) -> list:
        if self._host.has_service("updates"):
            svc = self._host.get_service("updates")
            if hasattr(svc, "get_ue4ss_releases_for_content"):
                return svc.get_ue4ss_releases_for_content(owner, repo) or []
        return []

    def get_framework_releases_for_content(self) -> list:
        if self._host.has_service("updates"):
            svc = self._host.get_service("updates")
            if hasattr(svc, "get_framework_releases_for_content"):
                return svc.get_framework_releases_for_content() or []
        return []

    def get_updates_service(self):
        if self._host.has_service("updates"):
            return self._host.get_service("updates")
        return None

    # -----------------------------------------------------------------------
    # Staged validation (pre-download)
    # -----------------------------------------------------------------------

    def validate_staged(
        self,
        mods: list,
        game_id: str,
    ) -> Tuple[list, list]:
        """
        Returns (errors, warnings) ValidationResult lists.
        Fetches installed mod IDs from the mods service automatically.
        """
        validation_svc = self._host.get_service("validation")
        if not validation_svc:
            return [], []
        installed_ids: set = set()
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            installed_ids = {m.mod_id for m in mods_svc.scan() if m.mod_id}
        results = validation_svc.validate_staged(mods, game_id, installed_ids)
        errors   = [r for r in results if r.status == "error"]
        warnings = [r for r in results if r.status == "warn"]
        return errors, warnings

    # -----------------------------------------------------------------------
    # Dependency resolution + queue ordering
    # -----------------------------------------------------------------------

    def resolve_and_queue(
        self,
        mods: list,
        templates: list,
        other: list,
        game_id: str,
    ) -> Tuple[list, list]:
        """
        Resolve dependency install order for all staged items.

        Returns (ordered_items, missing_dep_ids).
        ordered_items is a flat list: [(item, category), ...] in correct order.
        """
        from ....models.mods.dependency_graph import resolve_install_order
        from ....models.descriptors.types import TemplateDescriptor, BinaryDescriptor

        available: dict = {}
        installed: dict = {}
        try:
            registry_svc = self._registry_svc()
            if registry_svc:
                for m in registry_svc.get_mods(game_id):
                    mid = getattr(m, "mod_id", "")
                    if mid:
                        available[mid] = m
            if game_id:
                from ....models.state.install import InstallStateManager
                from ....models.state.pipeline import InstallRecord
                installed = {
                    d.get("mod_id", ""): InstallRecord.from_dict(d)
                    for d in InstallStateManager(game_id).get_all()
                    if d.get("mod_id")
                }
        except Exception as exc:
            logger.warning(f"Failed to load registry/install state for dependency sort: {exc}")

        staged = mods + templates + other
        try:
            ordered, missing, _ = resolve_install_order(staged, available, installed)
        except Exception as exc:
            logger.warning(f"resolve_install_order failed: {exc}")
            ordered, missing = staged, []

        o_mods      = [x for x in ordered if not isinstance(x, (TemplateDescriptor, BinaryDescriptor))]
        o_templates = [x for x in ordered if isinstance(x, TemplateDescriptor)]
        o_other     = [x for x in ordered if isinstance(x, BinaryDescriptor)]

        queue_items = (
            [(m, "mod")      for m in o_mods]
            + [(t, "template") for t in o_templates]
            + [(o, "other")    for o in o_other]
        )
        return queue_items, missing

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def has_registry_service(self) -> bool:
        return bool(self._registry_svc())

    def _registry_svc(self):
        if self._host.has_service("registry"):
            return self._host.get_service("registry")
        return None
