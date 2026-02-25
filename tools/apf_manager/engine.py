"""
APF Manager — install engine.

Executes install.json descriptors to copy files, create directories, manage mods.txt, etc.
Environment variables available in paths:
  ${source_project}   — source project root
  ${build_dir}        — compiled binaries directory
  ${target_mods}      — UE4SS Mods/ directory (from UE4SS detection)
  ${target_logicmods} — Content/Paks/LogicMods/ (created if needed)
  ${mod_dir}          — this mod's source directory
  ${framework_mod}    — APFrameworkMod source directory
  ${mod_name}         — this mod's folder name
"""

from __future__ import annotations

import datetime
import glob as glob_module
import shutil
from pathlib import Path
from typing import Callable

from .config import APFConfig, APFState, InstalledModInfo
from .discovery import ModDiscovery, ModInfo
from .load_order import ModsTextManager
from .ue4ss import UE4SSDetectionResult


class InstallEngine:
    """Executes install.json descriptor steps for a set of mods."""

    def __init__(self, config: APFConfig, log: Callable[[str], None] | None = None):
        self.config = config.resolve()
        self._log = log or print
        self._mods_mgr = ModsTextManager()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def deploy(self, mod: ModInfo, state: APFState, detection: UE4SSDetectionResult,
               *, manual_step_cb: Callable[[list[dict]], None] | None = None) -> bool:
        """
        Install a single mod. Returns True on success.
        manual_step_cb is called with the list of 'before_install' steps before installing,
        and with 'after_install' steps after. The GUI can display a dialog from this callback.
        """
        env = self._env(mod.folder_name, detection)
        descriptor = mod.install_descriptor

        # --- Before-install manual steps ---
        before_steps = [s for s in mod.manual_steps if s.get("when") == "before_install"]
        if before_steps and manual_step_cb:
            manual_step_cb(before_steps)

        # --- External dep warnings ---
        self._check_external_deps(mod, detection)

        self._log(f"Installing {mod.display_name}...")

        # --- Execute install steps ---
        if not descriptor.get("install"):
            self._log(f"  [WARN] No install steps defined for {mod.folder_name}")
            return False

        for step in descriptor["install"]:
            try:
                self._execute_step(step, env, detection)
            except Exception as exc:
                self._log(f"  [ERROR] Step {step} failed: {exc}")
                return False

        # --- Record installation ---
        state.installed_mods[mod.folder_name] = InstalledModInfo(
            version=mod.version,
            deployed_at=datetime.datetime.now().isoformat(),
        )

        # --- After-install manual steps ---
        after_steps = [s for s in mod.manual_steps if s.get("when") == "after_install"]
        if after_steps and manual_step_cb:
            manual_step_cb(after_steps)

        self._log(f"  Done.")
        return True

    def deploy_all(self, mods: list[ModInfo], state: APFState,
                   detection: UE4SSDetectionResult) -> bool:
        """Deploy all mods in list order. Returns True if all succeeded."""
        ok = True
        for mod in mods:
            if not self.deploy(mod, state, detection):
                ok = False
        return ok

    def uninstall(self, mod: ModInfo, state: APFState,
                  detection: UE4SSDetectionResult) -> None:
        """Remove a mod's deployed files and mods.txt entry."""
        env = self._env(mod.folder_name, detection)
        descriptor = mod.install_descriptor

        self._log(f"Uninstalling {mod.display_name}...")
        for step in descriptor.get("uninstall", []):
            try:
                self._execute_step(step, env, detection)
            except Exception as exc:
                self._log(f"  [WARN] Uninstall step {step} failed: {exc}")

        # Remove from mods.txt
        mods_txt = detection.mods_dir / "mods.txt"
        if mods_txt.exists():
            known = {mod.folder_name}
            self._mods_mgr.remove_mod(mods_txt, mod.folder_name, known)

        if mod.folder_name in state.installed_mods:
            del state.installed_mods[mod.folder_name]
        self._log(f"  Done.")

    def clean(self, mod_names: list[str], state: APFState,
              detection: UE4SSDetectionResult) -> None:
        """Remove deployed mod folders directly."""
        for name in mod_names:
            target = detection.mods_dir / name
            if target.exists():
                shutil.rmtree(target)
                self._log(f"Removed {name}")
            if name in state.installed_mods:
                del state.installed_mods[name]

    # -------------------------------------------------------------------------
    # Step execution
    # -------------------------------------------------------------------------

    def _execute_step(self, step: dict, env: dict[str, str],
                      detection: UE4SSDetectionResult) -> None:
        if "copy" in step:
            src = self._resolve(step["copy"], env)
            dst = self._resolve(step["to"], env)
            self._copy_file(src, dst)

        elif "copy_preserve" in step:
            src = self._resolve(step["copy_preserve"], env)
            dst = self._resolve(step["to"], env)
            dst_path = Path(dst) / Path(src).name
            if not dst_path.exists():
                self._copy_file(src, dst)
            else:
                self._log(f"  Preserved existing {dst_path.name}")

        elif "copy_glob" in step:
            pattern = self._resolve(step["copy_glob"], env)
            dst = self._resolve(step["to"], env)
            for f in glob_module.glob(pattern):
                self._copy_file(f, dst)

        elif "copy_tree" in step:
            src = self._resolve(step["copy_tree"], env)
            dst = self._resolve(step["to"], env)
            self._copy_tree(src, dst)

        elif "create_file" in step:
            path = Path(self._resolve(step["create_file"], env))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(step.get("content", ""), encoding="utf-8")
            self._log(f"  Created {path.name}")

        elif "remove_tree" in step:
            path = Path(self._resolve(step["remove_tree"], env))
            if path.exists():
                shutil.rmtree(path)
                self._log(f"  Removed {path}")

        elif "ensure_mods_txt" in step:
            self._ensure_mods_txt(step["ensure_mods_txt"], detection)

        elif "ensure_dir" in step:
            path = Path(self._resolve(step["ensure_dir"], env))
            path.mkdir(parents=True, exist_ok=True)
            self._log(f"  Ensured directory {path}")

    def _copy_file(self, src: str, dst_dir: str) -> None:
        src_path = Path(src)
        dst_path = Path(dst_dir)
        if not src_path.exists():
            raise FileNotFoundError(f"Source not found: {src_path}")
        dst_path.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path / src_path.name)
        self._log(f"  Copied {src_path.name} → {dst_path}")

    def _copy_tree(self, src: str, dst: str) -> None:
        src_path = Path(src)
        dst_path = Path(dst)
        if not src_path.exists():
            raise FileNotFoundError(f"Source tree not found: {src_path}")
        if dst_path.exists():
            shutil.rmtree(dst_path)
        shutil.copytree(src_path, dst_path)
        self._log(f"  Copied tree {src_path.name}/ → {dst_path}")

    def _ensure_mods_txt(self, entry: str, detection: UE4SSDetectionResult) -> None:
        """Add a mod entry to mods.txt using ModsTextManager (correct path: mods_dir/mods.txt)."""
        mods_txt = detection.mods_dir / "mods.txt"
        if not mods_txt.exists():
            self._log(f"  [WARN] mods.txt not found at {mods_txt}")
            return
        mod_name = entry.split(":")[0].strip()
        # We don't have the full known_ap_mods set here, but we can pass the mod name at minimum
        known: set[str] = {mod_name}
        self._mods_mgr.add_mod(mods_txt, mod_name, known)
        self._log(f"  mods.txt: ensured {mod_name}")

    def _check_external_deps(self, mod: ModInfo, detection: UE4SSDetectionResult) -> None:
        """Warn if any requires_external mods are not present in mods.txt."""
        if not mod.requires_external:
            return
        mods_txt = detection.mods_dir / "mods.txt"
        if not mods_txt.exists():
            return
        content = mods_txt.read_text(encoding="utf-8", errors="replace")
        for ext_dep in mod.requires_external:
            if ext_dep not in content:
                self._log(
                    f"  [WARN] {mod.display_name} requires '{ext_dep}' "
                    f"but it is not found in mods.txt. "
                    f"Please install '{ext_dep}' manually."
                )

    # -------------------------------------------------------------------------
    # Environment
    # -------------------------------------------------------------------------

    def _env(self, mod_folder: str, detection: UE4SSDetectionResult) -> dict[str, str]:
        cfg = self.config
        src = Path(cfg.source_project)
        return {
            "source_project": str(src),
            "build_dir": str(Path(cfg.build_dir)),
            "target_mods": str(detection.mods_dir),
            "target_logicmods": str(detection.logicmods_dir),
            "mod_dir": str(src / "Mods" / mod_folder),
            "framework_mod": str(src / "Mods" / "APFrameworkMod"),
            "mod_name": mod_folder,
        }

    def _resolve(self, s: str, env: dict[str, str]) -> str:
        for k, v in env.items():
            s = s.replace(f"${{{k}}}", v)
        return s
