"""DiagnosticsController — validation and log packaging logic."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..models.validation import DiagValidationItem, PackageResult
from .log_packager import LogPackager

if TYPE_CHECKING:
    from ....core.models.config import GameProfile
    from ....core.models.ue.result import DetectionResult


class DiagnosticsController:
    def __init__(self, host) -> None:
        self._host = host

    def run_validation(
        self,
        detection: Optional["DetectionResult"],
    ) -> list[DiagValidationItem]:
        items: list[DiagValidationItem] = []

        if not detection:
            return items

        ue4ss_dir_str = (
            str(detection.ue4ss.ue4ss_dir)
            if (detection.ue4ss and detection.ue4ss.ue4ss_dir)
            else ""
        )
        items.append(DiagValidationItem(
            label="UE4SS detected",
            detail=ue4ss_dir_str,
            status="ok" if detection.valid else "error",
        ))

        missing = detection.ue4ss.missing if detection.ue4ss else []
        for m in missing:
            items.append(DiagValidationItem(label=f"Missing: {m}", detail="", status="error"))

        validation_svc = self._host.get_service("validation")
        mods_svc = self._host.get_service("mods")
        if validation_svc and mods_svc:
            mods = mods_svc.scan()
            svc_results = validation_svc.validate_installed(mods, detection)
            has_issues = False
            for r in svc_results:
                if r.status != "ok":
                    items.append(DiagValidationItem(
                        label=f"{r.source}: {r.label}",
                        detail=r.detail,
                        status=r.status,
                    ))
                    has_issues = True
            if not has_issues:
                items.append(DiagValidationItem(
                    label="All mod checks passed", detail="", status="ok"
                ))
        else:
            items.append(DiagValidationItem(
                label="Mod validation skipped",
                detail="Validation service not available",
                status="warn",
            ))

        return items

    def package_logs(
        self,
        profile: "GameProfile",
        detection: "DetectionResult",
        folder: str,
    ) -> PackageResult:
        packager = LogPackager(profile, detection)
        filename = LogPackager.suggested_filename(profile.display_name)
        out_path = Path(folder) / filename
        included = packager.collect(out_path)
        return PackageResult(out_path=out_path, included=included)

    def get_log_paths(self, profile: "GameProfile") -> list[Path]:
        detection = self._host.get_detection()
        paths: list[Path] = []
        if not detection or not detection.ue4ss:
            return paths
        _mods = detection.ue4ss.mods_dir
        _ue4ss = detection.ue4ss.ue4ss_dir
        if _mods:
            paths.append(_mods / "APFrameworkMod" / "ap_framework.log")
        if _ue4ss:
            paths.append(_ue4ss / "UE4SS.log")
        return paths
