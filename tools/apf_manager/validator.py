"""
APF Manager — installation validator.

Runs validation checks defined in each mod's install.json 'validate' array,
plus global checks (DLLs, config JSON, mods.txt).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .config import APFConfig, APFState
from .discovery import ModDiscovery
from .ue4ss import UE4SSDetectionResult


class Validator:
    def __init__(self, config: APFConfig, discovery: ModDiscovery, state: APFState,
                 detection: UE4SSDetectionResult,
                 log: Callable[[str], None] | None = None):
        self.config = config.resolve()
        self.discovery = discovery
        self.state = state
        self.detection = detection
        self._log = log or print

    def validate_all(self) -> list[tuple[str, str, str]]:
        """
        Run all validation checks for installed mods.
        Returns list of (status, label, detail) where status is 'OK'|'WARN'|'ERROR'.
        """
        results: list[tuple[str, str, str]] = []

        if not self.detection.valid:
            results.append(("ERROR", "UE4SS detection", f"Not valid: {', '.join(self.detection.missing)}"))
            return results

        installed = set(self.state.installed_mods.keys())

        for mod in self.discovery.discover():
            if mod.folder_name not in installed:
                continue
            env = self._env(mod.folder_name)
            for check in mod.install_descriptor.get("validate", []):
                label = mod.folder_name

                if "exists" in check:
                    path = Path(self._resolve(check["exists"], env))
                    if path.exists():
                        size = (f"{path.stat().st_size:,} bytes" if path.is_file() else "dir")
                        results.append(("OK", f"{label}: {path.name}", size))
                    else:
                        results.append(("ERROR", f"{label}: {path.name}", f"Missing: {path}"))

                elif "valid_json" in check:
                    path = Path(self._resolve(check["valid_json"], env))
                    if not path.exists():
                        results.append(("ERROR", f"{label}: {path.name}", f"Missing: {path}"))
                    else:
                        try:
                            json.loads(path.read_text(encoding="utf-8"))
                            results.append(("OK", f"{label}: {path.name}", "valid JSON"))
                        except Exception as exc:
                            results.append(("ERROR", f"{label}: {path.name}", f"Invalid JSON: {exc}"))

                elif "mods_txt_contains" in check:
                    mod_name = check["mods_txt_contains"]
                    mods_txt = self.detection.mods_dir / "mods.txt"
                    if not mods_txt.exists():
                        results.append(("WARN", f"{label}: mods.txt", f"Not found at {mods_txt}"))
                    elif mod_name in mods_txt.read_text(encoding="utf-8", errors="replace"):
                        results.append(("OK", f"{label}: mods.txt", f"Contains {mod_name}"))
                    else:
                        results.append(("ERROR", f"{label}: mods.txt", f"Missing entry for {mod_name}"))

        # Global: framework config
        fw_config = self.detection.mods_dir / "APFrameworkMod" / "framework_config.json"
        if "APFrameworkMod" in installed:
            if fw_config.exists():
                try:
                    json.loads(fw_config.read_text(encoding="utf-8"))
                    results.append(("OK", "framework_config.json", "valid JSON"))
                except Exception as exc:
                    results.append(("ERROR", "framework_config.json", f"Invalid JSON: {exc}"))
            else:
                results.append(("WARN", "framework_config.json", f"Not found at {fw_config}"))

        return results

    def _env(self, mod_folder: str) -> dict[str, str]:
        cfg = self.config
        src = Path(cfg.source_project)
        return {
            "source_project": str(src),
            "build_dir": str(Path(cfg.build_dir)),
            "target_mods": str(self.detection.mods_dir),
            "target_logicmods": str(self.detection.logicmods_dir),
            "mod_dir": str(src / "Mods" / mod_folder),
            "framework_mod": str(src / "Mods" / "APFrameworkMod"),
            "mod_name": mod_folder,
        }

    def _resolve(self, s: str, env: dict[str, str]) -> str:
        for k, v in env.items():
            s = s.replace(f"${{{k}}}", v)
        return s
