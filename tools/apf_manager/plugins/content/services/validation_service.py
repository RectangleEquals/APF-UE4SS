"""
ValidationService — comprehensive mod install/staging/cache validation.

Registered as the "validation" service by the mods plugin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .mod_service import ModInfo
    from ....core.ue4ss import UE4SSResult


@dataclass
class ValidationResult:
    label: str
    detail: str
    status: str    # "ok" | "warn" | "error"
    source: str    # folder_name or context label


class ValidationService:
    def __init__(self, host) -> None:
        self._host = host

    # -----------------------------------------------------------------------
    # validate_installed — full health check against the deployed game state
    # -----------------------------------------------------------------------

    def validate_installed(
        self,
        mods: list,
        detection: Optional["UE4SSResult"],
    ) -> list[ValidationResult]:
        results: list[ValidationResult] = []

        # 1. UE4SS detected
        if detection is None or not detection.valid:
            results.append(ValidationResult(
                label="UE4SS not detected",
                detail="UE4SS installation could not be found.",
                status="error",
                source="UE4SS",
            ))
            return results  # Can't validate further without UE4SS

        # Build lookup sets
        ap_mods = [m for m in mods if getattr(m, "is_ap_mod", False)]
        mod_by_id = {m.mod_id: m for m in ap_mods if m.mod_id}
        mod_by_folder = {m.folder_name: m for m in mods}

        # 2. Framework mod present
        from ..utils.registry.resolver import _is_framework_mod_id
        fw_mods = [m for m in ap_mods if _is_framework_mod_id(m.mod_id)]
        if not fw_mods:
            results.append(ValidationResult(
                label="Framework mod missing",
                detail="No AP Framework mod found in Mods directory.",
                status="error",
                source="Framework",
            ))
        else:
            fw_mod = fw_mods[0]
            # 3. Framework mod orphaned (not tracked by APF Manager)
            if getattr(fw_mod, "is_orphaned", False):
                results.append(ValidationResult(
                    label="Framework mod not managed",
                    detail="Framework mod found but not installed by APF Manager.",
                    status="warn",
                    source=fw_mod.folder_name,
                ))

            # 4. Framework mod is first among AP mods in load order
            deploy_svc = self._host.get_service("deploy")
            if deploy_svc:
                order = deploy_svc.get_load_order()
                ap_in_order = [n for n in order if n in {m.folder_name for m in ap_mods}]
                if ap_in_order and ap_in_order[0] != fw_mod.folder_name:
                    results.append(ValidationResult(
                        label="Framework mod not first",
                        detail=f"'{fw_mod.folder_name}' must be first among AP mods in load order.",
                        status="error",
                        source=fw_mod.folder_name,
                    ))

        # 5. Dependency satisfaction
        for mod in ap_mods:
            for dep_str in getattr(mod, "depends", []):
                dep_id = dep_str.split(" ")[0].strip()
                if dep_id not in mod_by_id:
                    results.append(ValidationResult(
                        label=f"Missing dependency: {dep_id}",
                        detail=f"Required by {mod.display_name}.",
                        status="error",
                        source=mod.folder_name,
                    ))

        # 6. Incompatibility
        for mod in ap_mods:
            for incompat_id in getattr(mod, "incompatible", []):
                incompat_base = incompat_id.split(" ")[0].strip()
                if incompat_base in mod_by_id:
                    results.append(ValidationResult(
                        label=f"Incompatible: {incompat_base}",
                        detail=f"{mod.display_name} is incompatible with {incompat_base}.",
                        status="error",
                        source=mod.folder_name,
                    ))

        # 7. Duplicate mod_ids
        seen_ids: dict[str, str] = {}
        for mod in ap_mods:
            if mod.mod_id in seen_ids:
                results.append(ValidationResult(
                    label=f"Duplicate mod_id: {mod.mod_id}",
                    detail=f"Shared by {seen_ids[mod.mod_id]} and {mod.folder_name}.",
                    status="error",
                    source=mod.folder_name,
                ))
            else:
                seen_ids[mod.mod_id] = mod.folder_name

        # 8. BPModLoaderMod for Blueprint mods
        has_bp_mods = any("blueprint" in getattr(m, "components", []) for m in ap_mods)
        if has_bp_mods and detection.mods_dir:
            bpml_dir = detection.mods_dir / "BPModLoaderMod"
            bpml_exists = bpml_dir.is_dir()
            deploy_svc = self._host.get_service("deploy")
            bpml_enabled = (
                deploy_svc.mods_txt.is_enabled("BPModLoaderMod")
                if deploy_svc and deploy_svc.mods_txt
                else bpml_exists
            )
            if not bpml_exists or not bpml_enabled:
                results.append(ValidationResult(
                    label="BPModLoaderMod missing or disabled",
                    detail="Required for Blueprint Logic Mods (included with UE4SS releases).",
                    status="warn",
                    source="BPModLoaderMod",
                ))

        # 9. BP pak files deployed
        for mod in ap_mods:
            if "blueprint" in getattr(mod, "components", []):
                for pak in getattr(mod, "bp_pak_files", []):
                    if detection.logicmods_dir:
                        if not (detection.logicmods_dir / pak).exists():
                            results.append(ValidationResult(
                                label=f"Missing pak: {pak}",
                                detail=f"Expected in Content/Paks/LogicMods/ for {mod.display_name}.",
                                status="warn",
                                source=mod.folder_name,
                            ))
                    else:
                        results.append(ValidationResult(
                            label="LogicMods directory not found",
                            detail="Content/Paks/LogicMods/ does not exist.",
                            status="warn",
                            source=mod.folder_name,
                        ))
                        break

        # 10. C++ dll present
        for mod in ap_mods:
            if "cpp" in getattr(mod, "components", []) and detection.mods_dir:
                dll_path = detection.mods_dir / mod.folder_name / "dlls" / "main.dll"
                if not dll_path.exists():
                    results.append(ValidationResult(
                        label="C++ dll not found",
                        detail=f"dlls/main.dll missing for {mod.display_name}.",
                        status="warn",
                        source=mod.folder_name,
                    ))

        return results

    # -----------------------------------------------------------------------
    # validate_staged — pre-download validation
    # -----------------------------------------------------------------------

    def validate_staged(
        self,
        staged: list,
        game_id: str,
        installed_mod_ids: Optional[set] = None,
    ) -> list[ValidationResult]:
        """
        Pre-download/pre-install validation.

        Dependency chain enforced:
        - UE4SS / framework binaries (install_type in "ue4ss"/"framework_binary"):
            no mod-level validation — they are self-contained installs.
        - Non-AP mods (mod_id empty, not "other"):
            require UE4SS; no framework dependency.
        - AP mods (non-empty mod_id, not framework):
            require UE4SS installed/staged + core framework mod installed/staged.
        - Core framework mods:
            require UE4SS installed/staged.
        """
        results: list[ValidationResult] = []
        installed_mod_ids = installed_mod_ids or set()

        from ..utils.registry.resolver import _is_framework_mod_id

        # Partition staged items by type — "other" items (UE4SS / framework binaries)
        # skip ALL mod-level validation rules.
        def _is_other(m) -> bool:
            return getattr(m, "install_type", "") in ("ue4ss", "framework_binary") \
                or getattr(m, "category", "") == "other"

        mod_items = [m for m in staged if not _is_other(m)]

        staged_ids = {getattr(m, "mod_id", "") for m in mod_items if getattr(m, "mod_id", "")}
        all_ids = staged_ids | installed_mod_ids

        ap_mods = [m for m in mod_items
                   if getattr(m, "mod_id", "")
                   and not _is_framework_mod_id(getattr(m, "mod_id", ""))]
        fw_mods = [m for m in mod_items
                   if _is_framework_mod_id(getattr(m, "mod_id", ""))]

        # 1. Framework requirement — only AP mods require it (not non-AP, not "other")
        if ap_mods:
            has_fw = bool(fw_mods) or any(_is_framework_mod_id(mid) for mid in installed_mod_ids)
            if not has_fw:
                registry_svc = self._host.get_service("registry")
                candidates = registry_svc.get_framework_candidates(game_id) if registry_svc else []
                if not candidates:
                    results.append(ValidationResult(
                        label="No framework mod candidate",
                        detail="AP mods require a core framework mod. Add a registry that includes one.",
                        status="error",
                        source="Framework",
                    ))

        # 2. Duplicate mod_ids in staged list
        seen: dict[str, int] = {}
        for m in mod_items:
            mid = getattr(m, "mod_id", "")
            if mid:
                seen[mid] = seen.get(mid, 0) + 1
        for mid, count in seen.items():
            if count > 1:
                results.append(ValidationResult(
                    label=f"Duplicate: {mid}",
                    detail=f"Staged {count} times.",
                    status="error",
                    source=mid,
                ))

        # 3. Dependencies satisfied by staged ∪ installed
        for mod in mod_items:
            for dep_str in getattr(mod, "depends", []) or getattr(mod, "manifest", {}).get("depends", []):
                dep_id = dep_str.split(" ")[0].strip()
                if dep_id not in all_ids:
                    results.append(ValidationResult(
                        label=f"Missing dependency: {dep_id}",
                        detail=f"Not staged or installed — required by {getattr(mod, 'mod_id', '?')}.",
                        status="warn",
                        source=getattr(mod, "mod_id", "?"),
                    ))

        # 4. Incompatibilities within staged set
        for mod in mod_items:
            for incompat_id in getattr(mod, "incompatible", []) or getattr(mod, "manifest", {}).get("incompatible", []):
                incompat_base = incompat_id.split(" ")[0].strip()
                if incompat_base in staged_ids:
                    results.append(ValidationResult(
                        label=f"Incompatible: {incompat_base}",
                        detail=f"Conflict within staged items.",
                        status="error",
                        source=getattr(mod, "mod_id", "?"),
                    ))

        return results

    # -----------------------------------------------------------------------
    # validate_cached — pre-install validation
    # -----------------------------------------------------------------------

    def validate_cached(
        self,
        cached: list,
        detection: Optional["UE4SSResult"],
    ) -> list[ValidationResult]:
        installed_mod_ids: set = set()
        if detection and detection.mods_dir:
            mods_svc = self._host.get_service("mods")
            if mods_svc:
                installed_mod_ids = {m.mod_id for m in mods_svc.get_ap_mods() if m.mod_id}

        game_id = ""
        if detection:
            mods_svc = self._host.get_service("mods")
            if mods_svc:
                from ..utils.registry.resolver import _is_framework_mod_id
                for m in mods_svc.get_ap_mods():
                    if m.mod_id and _is_framework_mod_id(m.mod_id):
                        parts = m.mod_id.split(".")
                        if len(parts) >= 2:
                            game_id = parts[1]
                        break

        results = self.validate_staged(cached, game_id, installed_mod_ids)

        # Disk space check
        if detection and detection.mods_dir:
            import shutil as _shutil
            try:
                drive = detection.mods_dir.anchor
                _, _, free = _shutil.disk_usage(drive)
                if free < 100 * 1024 * 1024:  # < 100 MB
                    results.append(ValidationResult(
                        label="Low disk space",
                        detail=f"Less than 100 MB free on {drive}.",
                        status="warn",
                        source="Disk",
                    ))
            except Exception as exc:
                self._host.log(f"[validation] WARN: disk_usage check failed: {exc}")

        return results
