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
    from ...core.ue4ss import UE4SSResult


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
        fw_mods = [m for m in ap_mods if m.mod_id.endswith(".framework")]
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
        results: list[ValidationResult] = []
        installed_mod_ids = installed_mod_ids or set()

        staged_ids = {getattr(m, "mod_id", "") for m in staged if getattr(m, "mod_id", "")}
        all_ids = staged_ids | installed_mod_ids

        # 1. Framework candidate in registry (if non-framework mods staged)
        non_fw_staged = [m for m in staged if not getattr(m, "mod_id", "").endswith(".framework")]
        if non_fw_staged:
            has_fw = any(getattr(m, "mod_id", "").endswith(".framework") for m in staged) or \
                     any(mid.endswith(".framework") for mid in installed_mod_ids)
            if not has_fw:
                registry_svc = self._host.get_service("registry")
                if registry_svc:
                    candidates = registry_svc.get_framework_candidates(game_id)
                    if not candidates:
                        results.append(ValidationResult(
                            label="No framework mod candidate",
                            detail="AP Framework mod is required but not in any registry.",
                            status="error",
                            source="Framework",
                        ))

        # 2. Duplicate mod_ids in staged list
        seen: dict[str, int] = {}
        for m in staged:
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
        for mod in staged:
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
        for mod in staged:
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
                for m in mods_svc.get_ap_mods():
                    if m.mod_id and m.mod_id.endswith(".framework"):
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
            except Exception:
                pass

        return results
