"""
LogPackager — collects diagnostic files and bundles them into a timestamped ZIP.

ZIP contents:
    environment.json      -- APF Manager/framework/apworld versions, OS, Python, dev mode
    detection.json        -- Full flat DetectionResult serialization
    mods.json             -- All mods with load order, components, enabled/orphaned state
    install_state.json    -- InstallStateManager.get_all() for this game
    registries.json       -- User registries (url, game_id, cache state)
    validation.json       -- Full ValidationService results per mod
    UE4SS.log             -- from detection.ue4ss.ue4ss_dir / UE4SS.log
    UE4SS-settings.ini    -- from detection.ue4ss.ue4ss_dir / UE4SS-settings.ini
    ap_framework.log      -- resolved from framework_config.json logging.file
    framework_config.json -- sanitized (password replaced)
    session_state.json    -- from framework_mod output dir
    apf_manager.log       -- most-recent log file from ~/.apf_manager/logs/

Output: diagnostics_{game_name}_{timestamp}.zip
"""
from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ....core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from ....core.models.ue.result import DetectionResult
    from ....core.models.config import GameProfile


class LogPackager:
    def __init__(
        self,
        profile: "GameProfile",
        detection: "DetectionResult",
        host=None,
    ) -> None:
        self._profile = profile
        self._detection = detection
        self._host = host
        self._included: list[str] = []
        self._skipped: list[str] = []

    # -----------------------------------------------------------------------
    # Public entry point
    # -----------------------------------------------------------------------

    def collect(self, output_path: Path) -> tuple[list[str], list[str]]:
        """Build the ZIP. Returns (included, skipped) section name lists."""
        self._included = []
        self._skipped = []

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            self._add_environment(zf)
            self._add_detection(zf)
            self._add_mods(zf)
            self._add_install_state(zf)
            self._add_registries(zf)
            self._add_validation(zf)
            self._add_ue4ss_log(zf)
            self._add_ue4ss_settings(zf)
            self._add_framework_log(zf)
            self._add_framework_config(zf)
            self._add_session_state(zf)
            self._add_apf_manager_log(zf)

        return self._included, self._skipped

    @staticmethod
    def suggested_filename(game_name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in game_name)
        return f"diagnostics_{safe_name}_{ts}.zip"

    # -----------------------------------------------------------------------
    # Section collectors
    # -----------------------------------------------------------------------

    def _add_environment(self, zf: zipfile.ZipFile) -> None:
        try:
            fw_ver = apworld_ver = mgr_ver = "?"
            try:
                from .....__version__ import __version__, __framework_version__
                mgr_ver = __version__
                fw_ver = __framework_version__
            except Exception:
                pass
            dev_mode = getattr(self._host, "dev_mode", False) if self._host else False
            data = {
                "apf_manager_version": mgr_ver,
                "framework_version": fw_ver,
                "apworld_version": apworld_ver,
                "python_version": sys.version,
                "os_version": platform.version(),
                "platform": platform.platform(),
                "is_dev_mode": dev_mode,
                "generated_at": datetime.now().isoformat(),
            }
            zf.writestr("environment.json", json.dumps(data, indent=2))
            self._included.append("environment.json")
            logger.debug("environment.json added")
        except Exception as exc:
            logger.warning(f"Failed to collect environment.json: {exc}")
            self._skipped.append("environment.json")

    def _add_detection(self, zf: zipfile.ZipFile) -> None:
        try:
            d = self._detection
            ue4ss = d.ue4ss if d else None
            platform_det = d.platform if d else None
            fw_bins = d.framework_binaries if d else None
            fw_mod = d.framework_mod if d else None

            def _str(p) -> Optional[str]:
                return str(p) if p else None

            data: dict = {
                "is_ue_game": getattr(d, "is_ue_game", False) if d else False,
                "valid": getattr(d, "valid", False) if d else False,
            }
            if platform_det:
                data["platform"] = {
                    "platform_dir": _str(getattr(platform_det, "platform_dir", None)),
                }
            if ue4ss:
                data["ue4ss"] = {
                    "ue4ss_dir": _str(getattr(ue4ss, "ue4ss_dir", None)),
                    "mods_dir": _str(getattr(ue4ss, "mods_dir", None)),
                    "logicmods_dir": _str(getattr(ue4ss, "logicmods_dir", None)),
                    "missing": list(getattr(ue4ss, "missing", [])),
                }
            if fw_bins:
                data["framework_binaries"] = {
                    "installed": getattr(fw_bins, "installed", False),
                }
            if fw_mod:
                data["framework_mod"] = {
                    "mod_dir": _str(getattr(fw_mod, "mod_dir", None)),
                    "framework_config_path": _str(getattr(fw_mod, "framework_config_path", None)),
                }
            zf.writestr("detection.json", json.dumps(data, indent=2, default=str))
            self._included.append("detection.json")
            logger.debug("detection.json added")
        except Exception as exc:
            logger.warning(f"Failed to collect detection.json: {exc}")
            self._skipped.append("detection.json")

    def _add_mods(self, zf: zipfile.ZipFile) -> None:
        try:
            mods_svc = self._host.get_service("mods") if self._host else None
            deploy_svc = self._host.get_service("deploy") if self._host else None
            if not mods_svc:
                logger.warning("mods service unavailable -- skipping mods.json")
                self._skipped.append("mods.json")
                return

            mods = mods_svc.scan()
            load_order = deploy_svc.get_load_order() if deploy_svc else []
            order_set = set(load_order)

            mods_list = []
            for mod in mods:
                mods_list.append({
                    "folder_name": getattr(mod, "folder_name", ""),
                    "mod_id": getattr(mod, "mod_id", ""),
                    "name": getattr(mod, "display_name", "") or getattr(mod, "name", ""),
                    "version": getattr(mod, "version", ""),
                    "author": getattr(mod, "author", ""),
                    "components": list(getattr(mod, "components", [])),
                    "is_ap_mod": getattr(mod, "is_ap_mod", False),
                    "is_orphaned": getattr(mod, "is_orphaned", False),
                    "in_load_order": getattr(mod, "folder_name", "") in order_set,
                    "enabled": getattr(mod, "folder_name", "") in order_set,
                    "depends": list(getattr(mod, "depends", [])),
                    "incompatible": list(getattr(mod, "incompatible", [])),
                })

            data = {"load_order": list(load_order), "mods": mods_list}
            zf.writestr("mods.json", json.dumps(data, indent=2, default=str))
            self._included.append("mods.json")
            logger.debug(f"mods.json added ({len(mods_list)} mods)")
        except Exception as exc:
            logger.warning(f"Failed to collect mods.json: {exc}")
            self._skipped.append("mods.json")

    def _add_install_state(self, zf: zipfile.ZipFile) -> None:
        try:
            game_id = self._profile.game_id if self._profile else ""
            if not game_id:
                self._skipped.append("install_state.json")
                return
            from ....plugins.content.models.state.install import InstallStateManager
            records = InstallStateManager(game_id).get_all()
            zf.writestr("install_state.json", json.dumps(records, indent=2, default=str))
            self._included.append("install_state.json")
            logger.debug(f"install_state.json added ({len(records)} records)")
        except Exception as exc:
            logger.warning(f"Failed to collect install_state.json: {exc}")
            self._skipped.append("install_state.json")

    def _add_registries(self, zf: zipfile.ZipFile) -> None:
        try:
            if not self._host:
                self._skipped.append("registries.json")
                return
            regs = self._host.config.get_user_registries() if self._host.config else []
            data = [
                {"url": r.get("url", ""), "game_id": r.get("game_id", "")}
                for r in regs
            ]
            zf.writestr("registries.json", json.dumps(data, indent=2))
            self._included.append("registries.json")
            logger.debug(f"registries.json added ({len(data)} registries)")
        except Exception as exc:
            logger.warning(f"Failed to collect registries.json: {exc}")
            self._skipped.append("registries.json")

    def _add_validation(self, zf: zipfile.ZipFile) -> None:
        try:
            validation_svc = self._host.get_service("validation") if self._host else None
            mods_svc = self._host.get_service("mods") if self._host else None
            if not validation_svc or not mods_svc:
                logger.warning("validation or mods service unavailable -- skipping validation.json")
                self._skipped.append("validation.json")
                return
            mods = mods_svc.scan()
            results = validation_svc.validate_installed(mods, self._detection)
            data = [
                {
                    "source": r.source,
                    "label": r.label,
                    "detail": r.detail,
                    "status": r.status,
                }
                for r in results
            ]
            zf.writestr("validation.json", json.dumps(data, indent=2))
            self._included.append("validation.json")
            logger.debug(f"validation.json added ({len(data)} results)")
        except Exception as exc:
            logger.warning(f"Failed to collect validation.json: {exc}")
            self._skipped.append("validation.json")

    def _add_ue4ss_log(self, zf: zipfile.ZipFile) -> None:
        ue4ss = self._detection.ue4ss if self._detection else None
        ue4ss_dir = ue4ss.ue4ss_dir if ue4ss else None
        if not ue4ss_dir:
            logger.debug("ue4ss_dir not detected -- skipping UE4SS.log")
            self._skipped.append("UE4SS.log")
            return
        path = ue4ss_dir / "UE4SS.log"
        self._add_file(zf, path, "UE4SS.log")

    def _add_ue4ss_settings(self, zf: zipfile.ZipFile) -> None:
        ue4ss = self._detection.ue4ss if self._detection else None
        ue4ss_dir = ue4ss.ue4ss_dir if ue4ss else None
        if not ue4ss_dir:
            self._skipped.append("UE4SS-settings.ini")
            return
        path = ue4ss_dir / "UE4SS-settings.ini"
        self._add_file(zf, path, "UE4SS-settings.ini")

    def _add_framework_log(self, zf: zipfile.ZipFile) -> None:
        """Resolve framework log path from framework_config.json logging.file field."""
        fw_mod = self._detection.framework_mod if self._detection else None
        if not fw_mod:
            logger.debug("Framework mod not detected -- skipping ap_framework.log")
            self._skipped.append("ap_framework.log")
            return

        mod_dir = getattr(fw_mod, "mod_dir", None)
        cfg_path = getattr(fw_mod, "framework_config_path", None)

        log_file_setting = "ap_framework.log"  # default
        if cfg_path and Path(cfg_path).exists():
            try:
                raw = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
                log_file_setting = (
                    raw.get("logging", {}).get("file", "ap_framework.log") or "ap_framework.log"
                )
            except Exception as exc:
                logger.debug(f"Could not parse framework_config.json for log path: {exc}")

        if not log_file_setting:
            logger.debug("Framework log disabled (logging.file is empty string)")
            self._skipped.append("ap_framework.log (logging disabled)")
            return

        log_path = Path(log_file_setting)
        if not log_path.is_absolute() and mod_dir:
            log_path = Path(mod_dir) / log_file_setting

        self._add_file(zf, log_path, "ap_framework.log")

    def _add_framework_config(self, zf: zipfile.ZipFile) -> None:
        fw_mod = self._detection.framework_mod if self._detection else None
        if not fw_mod:
            self._skipped.append("framework_config.json")
            return
        cfg_path = getattr(fw_mod, "framework_config_path", None)
        if not cfg_path or not Path(cfg_path).exists():
            logger.debug(f"framework_config.json not found at {cfg_path}")
            self._skipped.append("framework_config.json")
            return
        try:
            sanitized = self._sanitize_config(Path(cfg_path))
            zf.writestr("framework_config.json", sanitized)
            self._included.append("framework_config.json (sanitized)")
            logger.debug(f"framework_config.json added from {cfg_path}")
        except Exception as exc:
            logger.warning(f"Failed to collect framework_config.json: {exc}")
            self._skipped.append("framework_config.json")

    def _add_session_state(self, zf: zipfile.ZipFile) -> None:
        fw_mod = self._detection.framework_mod if self._detection else None
        if not fw_mod:
            self._skipped.append("session_state.json")
            return
        mod_dir = getattr(fw_mod, "mod_dir", None)
        if not mod_dir:
            self._skipped.append("session_state.json")
            return
        path = Path(mod_dir) / "output" / "session_state.json"
        self._add_file(zf, path, "session_state.json")

    def _add_apf_manager_log(self, zf: zipfile.ZipFile) -> None:
        log_file = APFLogManager.get_log_file_path()
        if log_file and Path(log_file).exists():
            try:
                zf.write(str(log_file), "apf_manager.log")
                self._included.append("apf_manager.log")
                logger.debug(f"apf_manager.log added from {log_file}")
            except Exception as exc:
                logger.warning(f"Failed to include apf_manager.log: {exc}")
                self._skipped.append("apf_manager.log")
        else:
            logger.debug("No APF Manager log file found -- skipping apf_manager.log")
            self._skipped.append("apf_manager.log (no log file)")

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _add_file(self, zf: zipfile.ZipFile, path: Path, arcname: str) -> None:
        if path.exists():
            try:
                zf.write(str(path), arcname)
                self._included.append(arcname)
                logger.debug(f"{arcname} added from {path}")
            except Exception as exc:
                logger.warning(f"Failed to include {arcname} from {path}: {exc}")
                self._skipped.append(arcname)
        else:
            logger.debug(f"{arcname} not found at {path} -- skipping")
            self._skipped.append(arcname)

    @staticmethod
    def _sanitize_config(path: Path) -> str:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data.get("server"), dict):
                data["server"]["password"] = "[redacted]"
            return json.dumps(data, indent=2)
        except Exception:
            return path.read_text(encoding="utf-8", errors="replace")
