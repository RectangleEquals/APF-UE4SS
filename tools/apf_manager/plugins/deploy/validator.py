"""
Validator — runs install.json validate checks and dependency warnings.

ValidationResult status values: "ok" | "warn" | "error"
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.ue4ss import UE4SSResult
    from ..mods.mod_service import ModInfo
    from .mods_txt import ModsTextManager


@dataclass
class ValidationResult:
    status: str    # "ok" | "warn" | "error"
    label: str     # Short label shown in the UI row
    detail: str    # Longer description for tooltips / expand


class Validator:
    def __init__(
        self,
        detection: "UE4SSResult",
        mods_txt: "ModsTextManager",
        all_mods: list["ModInfo"],
    ) -> None:
        self._detection = detection
        self._mods_txt = mods_txt
        self._all_mods = all_mods
        self._mod_by_id = {m.mod_id: m for m in all_mods if m.mod_id}
        self._mod_by_folder = {m.folder_name: m for m in all_mods}

    # -----------------------------------------------------------------------
    # Per-mod validation
    # -----------------------------------------------------------------------

    def validate_mod(self, mod: "ModInfo") -> list[ValidationResult]:
        results: list[ValidationResult] = []

        # Run install.json validate checks
        for check in mod.validate_checks:
            results.append(self._run_check(check, mod))

        # Dependency checks
        results.extend(self._check_depends(mod))
        results.extend(self._check_incompatible(mod))
        results.extend(self._check_requires_external(mod))

        return results

    def validate_all(self) -> dict[str, list[ValidationResult]]:
        return {mod.folder_name: self.validate_mod(mod) for mod in self._all_mods}

    # -----------------------------------------------------------------------
    # Check dispatchers
    # -----------------------------------------------------------------------

    def _run_check(self, check, mod: "ModInfo") -> ValidationResult:
        from ...core.ue4ss import UE4SSResult  # noqa: F401 (type hint use)
        t = check.check_type
        p = check.params

        try:
            if t == "file_exists":
                return self._check_file_exists(p)
            elif t == "mod_enabled":
                return self._check_mod_enabled(p)
            elif t == "external_mod":
                return self._check_external_mod_present(p)
            else:
                return ValidationResult("warn", "Unknown check", f"Check type {t!r} is not recognised")
        except Exception as exc:
            return ValidationResult("error", "Check failed", str(exc))

    @staticmethod
    def _check_file_exists(p: dict) -> ValidationResult:
        path = Path(p.get("path", ""))
        if path.exists():
            return ValidationResult("ok", "File present", str(path))
        return ValidationResult("error", "File missing", f"Required file not found: {path}")

    def _check_mod_enabled(self, p: dict) -> ValidationResult:
        name = p.get("mod_name", "")
        if self._mods_txt.is_enabled(name):
            return ValidationResult("ok", f"{name} enabled", "")
        return ValidationResult("error", f"{name} not enabled", f"{name} must be enabled in mods.txt")

    def _check_external_mod_present(self, p: dict) -> ValidationResult:
        name = p.get("name", "")
        folder = self._detection.mods_dir / name if self._detection.mods_dir else None
        if folder and folder.is_dir():
            return ValidationResult("ok", f"{name} found", "")
        return ValidationResult("warn", f"{name} not found", f"External mod '{name}' was not found in Mods/")

    # -----------------------------------------------------------------------
    # Dependency checks
    # -----------------------------------------------------------------------

    def _check_depends(self, mod: "ModInfo") -> list[ValidationResult]:
        results = []
        for dep_str in mod.depends:
            dep_id = dep_str.split(" ")[0].strip()
            if dep_id not in self._mod_by_id:
                results.append(ValidationResult(
                    "error",
                    f"Missing: {dep_id}",
                    f"{mod.display_name} requires '{dep_id}' which is not installed.",
                ))
        return results

    def _check_incompatible(self, mod: "ModInfo") -> list[ValidationResult]:
        results = []
        for incompat_id in mod.incompatible:
            if incompat_id in self._mod_by_id:
                results.append(ValidationResult(
                    "error",
                    f"Conflict: {incompat_id}",
                    f"{mod.display_name} is incompatible with '{incompat_id}'.",
                ))
        return results

    def _check_requires_external(self, mod: "ModInfo") -> list[ValidationResult]:
        results = []
        for ext_name in mod.requires_external:
            folder = (
                self._detection.mods_dir / ext_name
                if self._detection.mods_dir else None
            )
            if not (folder and folder.is_dir()):
                results.append(ValidationResult(
                    "warn",
                    f"Needs: {ext_name}",
                    f"{mod.display_name} requires the external mod '{ext_name}' to be installed.",
                ))
        return results

    # -----------------------------------------------------------------------
    # Aggregate helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def worst_status(results: list[ValidationResult]) -> str:
        if any(r.status == "error" for r in results):
            return "error"
        if any(r.status == "warn" for r in results):
            return "warn"
        return "ok"
