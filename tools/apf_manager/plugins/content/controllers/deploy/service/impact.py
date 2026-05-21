"""DeployImpactMixin — uninstall impact analysis + template deployment for DeployService."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ......core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from ......core.models.ue.result import DetectionResult
    from ....models.state.pipeline import InstallRecord


class DeployImpactMixin:
    """Mixin for DeployService: get_uninstall_impact, template deploy/undeploy, component status."""

    def get_uninstall_impact(self, record: "InstallRecord") -> dict:
        """Return {affected_mods: list[InstallRecord], template_dirs_removed: list[str]}."""
        from ....models.state.install import InstallStateManager
        from ....models.state.pipeline import InstallRecord as _IR
        from ....models.mods.dependency_graph import resolve_uninstall_cascade
        if not self._profile:
            return {"affected_mods": [], "template_dirs_removed": []}

        all_records = [_IR.from_dict(d) for d in InstallStateManager(self._profile.game_id).get_all()]
        affected = resolve_uninstall_cascade(record, all_records)

        template_dirs: list[str] = []
        if record.content_type == "framework_mod":
            mods_svc = self._host.get_service("mods")
            if mods_svc:
                fw_dir = mods_svc.get_framework_mod_dir()
                if fw_dir:
                    templates_root = fw_dir / "Templates"
                    if templates_root.is_dir():
                        template_dirs = [str(templates_root)]

        return {"affected_mods": affected, "template_dirs_removed": template_dirs}

    def get_framework_uninstall_impact(self) -> dict:
        """
        Analyse the cascading damage caused by uninstalling the framework mod.

        Returns:
          {
            "affected_mods": [ModInfo, ...],    # installed AP mods with capabilities.include
            "template_dirs_removed": [Path, ...] # Template subdirs that would be deleted
          }
        """
        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return {"affected_mods": [], "template_dirs_removed": []}

        fw_dir = mods_svc.get_framework_mod_dir()
        affected: list = []
        template_dirs: list[Path] = []

        if fw_dir:
            templates_root = fw_dir / "Templates"
            if templates_root.is_dir():
                template_dirs = [templates_root]

        for mod in mods_svc.get_ap_mods():
            includes = mod.capabilities_includes
            if includes:
                affected.append(mod)

        return {
            "affected_mods": affected,
            "template_dirs_removed": template_dirs,
        }

    def get_component_status(self, mod_info, detection: "Optional[DetectionResult]") -> dict:
        """
        Return per-component presence status for a deployed mod.
        Keys: "lua", "cpp", "blueprint" — values: bool.
        """
        if not detection or not detection.ue4ss:
            return {}

        components = mod_info.components
        bp_pak_files = mod_info.bp_pak_files
        status = {}
        mods_dir = detection.ue4ss.mods_dir

        if "lua" in components:
            status["lua"] = bool(mods_dir and (
                mods_dir / mod_info.folder_name / "scripts" / "main.lua"
            ).exists())

        if "cpp" in components:
            status["cpp"] = bool(mods_dir and (
                mods_dir / mod_info.folder_name / "dlls" / "main.dll"
            ).exists())

        if "blueprint" in components:
            lm_dir = detection.ue4ss.logicmods_dir
            if bp_pak_files and lm_dir:
                status["blueprint"] = all(
                    (lm_dir / f).exists() for f in bp_pak_files
                )
            else:
                status["blueprint"] = False

        return status

    # -----------------------------------------------------------------------
    # Template deployment helpers
    # -----------------------------------------------------------------------

    def get_templates_dir(self, game_name: str) -> Optional[Path]:
        """
        Return <framework_mod_dir>/Templates/<game_name>/, or None if the
        framework mod is absent or in a conflict state.
        """
        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return None
        fw_dir = mods_svc.get_framework_mod_dir()
        if not fw_dir:
            return None
        return fw_dir / "Templates" / game_name

    def deploy_template(self, cache_path: Path, game_name: str) -> None:
        """
        Copy template files from cache_path into <framework_mod>/Templates/<game_name>/
        additively (existing files from other registries are not removed).
        """
        target = self.get_templates_dir(game_name)
        if not target:
            raise RuntimeError("Cannot deploy templates: framework mod not found or in conflict state")
        target.mkdir(parents=True, exist_ok=True)
        for src in cache_path.rglob("*"):
            if src.is_dir():
                continue
            rel = src.relative_to(cache_path)
            dst = target / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))

    def undeploy_template(self, game_name: str, file_paths: list[str]) -> None:
        """
        Remove specific files (given as paths relative to Templates/<game_name>/)
        from the framework mod's template directory. Only removes files this
        source contributed — does not touch files from other registries.
        """
        target = self.get_templates_dir(game_name)
        if not target:
            return
        for rel_path in file_paths:
            full = target / rel_path
            try:
                full.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning(f"Failed to remove template file '{rel_path}': {exc}")
        # Prune empty directories left behind
        for dirpath in sorted(target.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    dirpath.rmdir()
                except OSError as exc:
                    logger.debug("[impact] Could not prune directory %s (likely not empty): %s", dirpath, exc)

    def get_template_status(self, template_entry, game_name: str) -> dict:
        """
        Return {relative_path: bool} for each file expected from template_entry.
        True = file is present on disk in the framework mod's Templates dir.
        """
        target = self.get_templates_dir(game_name)
        if not target:
            return {}
        result = {}
        paths = getattr(template_entry, "file_paths", []) or []
        for rel_path in paths:
            result[rel_path] = (target / rel_path).exists()
        return result
