"""
InstallEngine — executes install.json step lists for a single mod.

Supported step types:
    copy            Copy src → dst (overwrites)
    copy_preserve   Copy src → dst only if dst does not exist
    copy_glob       Copy all files matching a glob pattern into dst_dir
    copy_tree       Recursively copy src_dir → dst_dir
    create_file     Write content string to a file
    remove_tree     Remove a directory tree
    ensure_dir      Create a directory (parents=True, exist_ok=True)
    ensure_mods_txt Add mod_name to mods.txt if absent

Environment variables available in all path/content params:
    ${source_project}   GameProfile.source_project
    ${build_dir}        GameProfile.build_dir
    ${target_mods}      UE4SSResult.mods_dir
    ${target_logicmods} UE4SSResult.mods_dir / "LogicMods"
    ${mod_dir}          Absolute path to this mod's folder
    ${framework_mod}    UE4SSResult.mods_dir / "APFrameworkMod"
    ${mod_name}         Mod folder name (folder_name attribute)
"""

from __future__ import annotations

import glob
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.ue4ss import UE4SSResult
    from ..mods.mod_service import ModInfo, InstallStep
    from .mods_txt import ModsTextManager


@dataclass
class StepResult:
    ok: bool
    message: str


class InstallEngine:
    """
    Executes a sequence of InstallStep objects for a given mod.

    Usage:
        engine = InstallEngine(profile, detection)
        results = engine.run_steps(mod_info.install_steps, mod_info)
    """

    def __init__(
        self,
        profile: "GameProfile",
        detection: "UE4SSResult",
        mods_txt: "ModsTextManager",
        log_fn=None,
    ) -> None:
        self._profile = profile
        self._detection = detection
        self._mods_txt = mods_txt
        self._log = log_fn or (lambda msg: None)
        self._tracker: Optional[list[Path]] = None

    # -----------------------------------------------------------------------
    # Public
    # -----------------------------------------------------------------------

    def run_steps(
        self,
        steps: list["InstallStep"],
        mod: "ModInfo",
        manifest_path: Optional[Path] = None,
    ) -> list[StepResult]:
        if manifest_path is not None:
            self._tracker = []
        env = self._build_env(mod)
        results = []
        for step in steps:
            result = self._run_step(step, env)
            results.append(result)
            self._log(f"[{'OK' if result.ok else 'ERR'}] {step.step_type}: {result.message}")
        if manifest_path is not None and self._tracker is not None:
            self._write_manifest(manifest_path, self._tracker)
        self._tracker = None
        return results

    def run_uninstall(
        self,
        steps: list["InstallStep"],
        mod: "ModInfo",
    ) -> list[StepResult]:
        env = self._build_env(mod)
        results = []
        for step in steps:
            result = self._run_step(step, env)
            results.append(result)
            self._log(f"[{'OK' if result.ok else 'ERR'}] {step.step_type} (uninstall): {result.message}")
        return results

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _build_env(self, mod: "ModInfo") -> dict[str, str]:
        d = self._detection
        mods_dir = str(d.mods_dir) if d.mods_dir else ""
        return {
            "source_project": self._profile.source_project or "",
            "build_dir": self._profile.build_dir or "",
            "target_mods": mods_dir,
            "target_logicmods": str(Path(mods_dir) / "LogicMods") if mods_dir else "",
            "mod_dir": str(mod.folder_path),
            "framework_mod": str(Path(mods_dir) / "APFrameworkMod") if mods_dir else "",
            "mod_name": mod.folder_name,
        }

    @staticmethod
    def _expand(value: str, env: dict[str, str]) -> str:
        """Replace ${key} placeholders with env values."""
        def _replace(m: re.Match) -> str:
            return env.get(m.group(1), m.group(0))
        return re.sub(r"\$\{(\w+)\}", _replace, value)

    def _run_step(self, step: "InstallStep", env: dict[str, str]) -> StepResult:
        p = {k: self._expand(str(v), env) for k, v in step.params.items()}
        t = step.step_type
        try:
            if t == "copy":
                return self._copy(p, overwrite=True)
            elif t == "copy_preserve":
                return self._copy(p, overwrite=False)
            elif t == "copy_glob":
                return self._copy_glob(p)
            elif t == "copy_tree":
                return self._copy_tree(p)
            elif t == "create_file":
                return self._create_file(p)
            elif t == "remove_tree":
                return _remove_tree(p)
            elif t == "ensure_dir":
                return _ensure_dir(p)
            elif t == "ensure_mods_txt":
                return self._ensure_mods_txt(p)
            else:
                return StepResult(ok=False, message=f"Unknown step type: {t!r}")
        except Exception as exc:
            return StepResult(ok=False, message=str(exc))

    # -----------------------------------------------------------------------
    # Step handlers (instance methods to access _tracker)
    # -----------------------------------------------------------------------

    def _copy(self, p: dict, overwrite: bool) -> StepResult:
        src = Path(p.get("src", ""))
        dst = Path(p.get("dst", ""))
        if not src.exists():
            return StepResult(ok=False, message=f"Source not found: {src}")
        if not overwrite and dst.exists():
            return StepResult(ok=True, message=f"Preserved existing: {dst.name}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if self._tracker is not None:
            self._tracker.append(dst)
        return StepResult(ok=True, message=f"{src.name} → {dst}")

    def _copy_glob(self, p: dict) -> StepResult:
        pattern = p.get("pattern", "")
        src_dir = Path(p.get("src_dir", "."))
        dst_dir = Path(p.get("dst_dir", ""))
        matches = list(glob.glob(str(src_dir / pattern)))
        if not matches:
            return StepResult(ok=False, message=f"No files matched: {pattern}")
        dst_dir.mkdir(parents=True, exist_ok=True)
        for f in matches:
            dst = dst_dir / Path(f).name
            shutil.copy2(f, dst)
            if self._tracker is not None:
                self._tracker.append(dst)
        return StepResult(ok=True, message=f"Copied {len(matches)} file(s) to {dst_dir}")

    def _copy_tree(self, p: dict) -> StepResult:
        src = Path(p.get("src", ""))
        dst = Path(p.get("dst", ""))
        if not src.is_dir():
            return StepResult(ok=False, message=f"Source directory not found: {src}")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        if self._tracker is not None:
            for f in dst.rglob("*"):
                if f.is_file():
                    self._tracker.append(f)
        return StepResult(ok=True, message=f"{src.name}/ → {dst}")

    def _create_file(self, p: dict) -> StepResult:
        path = Path(p.get("path", ""))
        content = p.get("content", "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if self._tracker is not None:
            self._tracker.append(path)
        return StepResult(ok=True, message=f"Created {path.name}")

    def _ensure_mods_txt(self, p: dict) -> StepResult:
        mod_name = p.get("mod_name", "")
        if not mod_name:
            return StepResult(ok=False, message="ensure_mods_txt: mod_name not specified")
        self._mods_txt.ensure_entry(mod_name, enabled=True)
        self._mods_txt.save()
        return StepResult(ok=True, message=f"mods.txt: ensured {mod_name}")

    # -----------------------------------------------------------------------
    # Manifest
    # -----------------------------------------------------------------------

    @staticmethod
    def _write_manifest(manifest_path: Path, files: list[Path]) -> None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "files": [str(f) for f in files],
        }
        manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# -----------------------------------------------------------------------
# Pure static step handlers (no file tracking)
# -----------------------------------------------------------------------

def _remove_tree(p: dict) -> StepResult:
    path = Path(p.get("path", ""))
    if not path.exists():
        return StepResult(ok=True, message=f"Already absent: {path.name}")
    shutil.rmtree(path)
    return StepResult(ok=True, message=f"Removed {path}")


def _ensure_dir(p: dict) -> StepResult:
    path = Path(p.get("path", ""))
    path.mkdir(parents=True, exist_ok=True)
    return StepResult(ok=True, message=f"Directory ready: {path}")
