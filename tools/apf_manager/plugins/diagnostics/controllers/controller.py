"""DiagnosticsController — validation and log packaging logic."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ....core.controllers.logging.manager import APFLogManager
from ..models.validation import DiagValidationItem, PackageResult
from .log_packager import LogPackager

logger = APFLogManager.get_logger(__name__)

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
            items.append(DiagValidationItem(
                label="No game selected",
                detail="Select a game profile to run diagnostics.",
                status="warn",
            ))
            return items

        # Basic detection checks
        items.append(DiagValidationItem(
            label="UE game detected",
            detail="",
            status="ok" if detection.is_ue_game else "error",
        ))

        platform_ok = bool(detection.platform and detection.platform.platform_dir)
        items.append(DiagValidationItem(
            label="Platform directory detected",
            detail=str(detection.platform.platform_dir) if platform_ok else "",
            status="ok" if platform_ok else "error",
        ))

        ue4ss_ok = bool(detection.ue4ss and detection.ue4ss.ue4ss_dir)
        ue4ss_dir_str = str(detection.ue4ss.ue4ss_dir) if ue4ss_ok else ""
        items.append(DiagValidationItem(
            label="UE4SS detected",
            detail=ue4ss_dir_str,
            status="ok" if ue4ss_ok else "error",
        ))

        missing = detection.ue4ss.missing if detection.ue4ss else []
        for m in missing:
            items.append(DiagValidationItem(label=f"Missing: {m}", detail="", status="error"))

        # Framework binaries
        fw_bins = detection.framework_binaries if detection else None
        fw_bins_ok = bool(fw_bins and getattr(fw_bins, "installed", False))
        items.append(DiagValidationItem(
            label="Framework binaries installed",
            detail="",
            status="ok" if fw_bins_ok else "warn",
        ))

        # Framework mod
        fw_mod = detection.framework_mod if detection else None
        fw_mod_ok = bool(fw_mod and getattr(fw_mod, "mod_dir", None))
        items.append(DiagValidationItem(
            label="Framework mod present",
            detail=str(fw_mod.mod_dir) if fw_mod_ok else "",
            status="ok" if fw_mod_ok else "warn",
        ))

        if fw_mod_ok:
            cfg_path = getattr(fw_mod, "framework_config_path", None)
            cfg_ok = bool(cfg_path and Path(cfg_path).exists())
            items.append(DiagValidationItem(
                label="framework_config.json exists",
                detail=str(cfg_path) if cfg_ok else "",
                status="ok" if cfg_ok else "warn",
            ))

        # Mod validation via ValidationService
        validation_svc = self._host.get_service("validation")
        mods_svc = self._host.get_service("mods")
        if validation_svc and mods_svc:
            mods = mods_svc.scan()
            ap_mods = [m for m in mods if getattr(m, "is_ap_mod", False)]
            orphaned = [m for m in ap_mods if getattr(m, "is_orphaned", False)]

            items.append(DiagValidationItem(
                label=f"AP mods installed",
                detail=f"{len(ap_mods)} mod(s), {len(orphaned)} orphaned",
                status="ok" if ap_mods else "warn",
            ))
            if orphaned:
                items.append(DiagValidationItem(
                    label=f"Orphaned mods detected",
                    detail=", ".join(m.folder_name for m in orphaned),
                    status="warn",
                ))

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
        packager = LogPackager(profile, detection, host=self._host)
        filename = LogPackager.suggested_filename(profile.display_name)
        out_path = Path(folder) / filename
        included, skipped = packager.collect(out_path)
        logger.info(
            f"Diagnostics package created: {filename} "
            f"({len(included)} sections included, {len(skipped)} skipped)"
        )
        return PackageResult(out_path=out_path, included=included, skipped=skipped)

    def get_log_paths(self, profile: "GameProfile") -> list[Path]:
        detection = self._host.get_detection()
        paths: list[Path] = []
        if not detection:
            return paths
        fw_mod = getattr(detection, "framework_mod", None)
        if fw_mod and getattr(fw_mod, "mod_dir", None):
            paths.append(Path(fw_mod.mod_dir) / "ap_framework.log")
        ue4ss = getattr(detection, "ue4ss", None)
        if ue4ss and getattr(ue4ss, "ue4ss_dir", None):
            paths.append(ue4ss.ue4ss_dir / "UE4SS.log")
        log_file = APFLogManager.get_log_file_path()
        if log_file:
            paths.append(Path(log_file))
        return paths
