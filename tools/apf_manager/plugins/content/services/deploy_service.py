"""
DeployService — service API for mod deployment operations.

Registered as the "deploy" service by the mods plugin.

Owns the shared ModsTextManager instance so all tabs share the same in-memory state.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ....core.config import GameProfile
    from ....core.ue4ss import UE4SSResult
    from ..utils.mods_txt import ModsTextManager
    from .mod_service import ModInfo, ModService
    from ..shared.data.content_base import ContentDescriptor
    from ..shared.data.pipeline_state import InstallRecord


def _classify_zip(zf) -> str:
    """Inspect a ZipFile TOC to determine the appropriate install target.

    Returns one of: "ue4ss" | "framework_bin" | "blueprint_pak" | "unknown"
    """
    names_lower = {info.filename.lower() for info in zf.infolist()}
    # UE4SS: has ue4ss/ folder containing UE4SS.dll (universal UE4SS marker)
    if any("ue4ss/ue4ss.dll" in n for n in names_lower):
        return "ue4ss"
    # Framework binary: has APFrameworkCore.dll
    if any("apframeworkcore.dll" in n for n in names_lower):
        return "framework_bin"
    # Standalone blueprint pak: ALL non-directory entries are .pak files
    non_dir = [n for n in names_lower if not n.endswith("/")]
    if non_dir and all(n.endswith(".pak") for n in non_dir):
        return "blueprint_pak"
    return "unknown"


class DeployService:
    def __init__(self, host) -> None:
        self._host = host
        self._mods_txt: Optional["ModsTextManager"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._profile: Optional["GameProfile"] = None
        self._lock = threading.Lock()

    # Called by PluginHost when game context changes
    def on_game_changed(self, profile: Optional["GameProfile"], detection: Optional["UE4SSResult"]) -> None:
        with self._lock:
            self._profile = profile
            self._detection = detection
            self._reload_mods_txt()

    def _reload_mods_txt(self) -> None:
        if self._detection and self._detection.mods_txt:
            from ..utils.mods_txt import ModsTextManager
            self._mods_txt = ModsTextManager(self._detection.mods_txt)
            self._mods_txt.load()
        else:
            self._mods_txt = None

    # -----------------------------------------------------------------------
    # Public API (inter-plugin)
    # -----------------------------------------------------------------------

    @property
    def mods_txt(self) -> Optional["ModsTextManager"]:
        return self._mods_txt

    def get_load_order(self) -> list[str]:
        with self._lock:
            return self._mods_txt.get_order() if self._mods_txt else []

    def set_enabled(self, folder_name: str, enabled: bool) -> None:
        with self._lock:
            if self._mods_txt:
                self._mods_txt.set_enabled(folder_name, enabled)
                self._mods_txt.save()

    def ensure_entry(self, folder_name: str, enabled: bool = True) -> None:
        with self._lock:
            if self._mods_txt:
                self._mods_txt.ensure_entry(folder_name, enabled)
                self._mods_txt.save()

    def reorder(self, order: list[str]) -> None:
        with self._lock:
            if self._mods_txt:
                enforced = self._enforce_framework_order(order)
                self._mods_txt.reorder(enforced)
                self._mods_txt.save()

    def _get_framework_folder(self) -> Optional[str]:
        """Return the framework mod folder name (delegates to ModService for pattern-correct detection)."""
        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return None
        fw_dir = mods_svc.get_framework_mod_dir()
        return fw_dir.name if fw_dir else None

    def _enforce_framework_order(self, order: list[str]) -> list[str]:
        """
        Ensure the framework mod precedes all other AP mods in the order list.
        This is a safety net; the UI cascade logic should maintain the invariant.
        """
        fw_folder = self._get_framework_folder()
        if not fw_folder or fw_folder not in order:
            return order

        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return order

        ap_folders = {mod.folder_name for mod in mods_svc.get_ap_mods()}
        result = list(order)
        fw_idx = result.index(fw_folder)

        # Find the first non-framework AP mod that appears before the framework mod
        for i in range(fw_idx):
            if result[i] in ap_folders and result[i] != fw_folder:
                # Move framework mod to just before that AP mod
                result.pop(fw_idx)
                result.insert(i, fw_folder)
                break

        return result

    def remove_entry(self, folder_name: str) -> None:
        """Remove a mod entry from mods.txt and save."""
        with self._lock:
            if self._mods_txt:
                self._mods_txt.remove_entry(folder_name)
                self._mods_txt.save()

    def reload(self) -> None:
        """Force re-read mods.txt from disk."""
        with self._lock:
            self._reload_mods_txt()

    # -----------------------------------------------------------------------
    # Typed deploy / undeploy (Phase F)
    # -----------------------------------------------------------------------

    def deploy_content(
        self,
        cache_path: "Path",
        content: "ContentDescriptor",
        detection: "Optional[UE4SSResult]",
        game_id: str = "",
    ) -> "InstallRecord":
        """Content-aware dispatch. Routes by content type, saves InstallRecord for mods."""
        from ..shared.data.content_types import ModDescriptor, TemplateDescriptor, BinaryDescriptor
        from ..shared.data.pipeline_state import InstallRecord
        from ..shared.data.install_state import InstallStateManager

        gid = game_id or content.game_id or (self._profile.game_id if self._profile else "")
        record = InstallRecord.from_content(content, gid)

        if isinstance(content, TemplateDescriptor):
            self._deploy_template_content(cache_path, content)
        elif isinstance(content, BinaryDescriptor):
            self._deploy_binary_content(cache_path, content, detection)
        elif isinstance(content, ModDescriptor):
            self._deploy_mod_content(cache_path, content, detection)
        else:
            raise TypeError(f"Unsupported content type: {content.content_type!r}")

        if gid and isinstance(content, ModDescriptor):
            InstallStateManager(gid).add_record(record)
        return record

    def _deploy_mod_content(
        self,
        cache_path: "Path",
        content: "ModDescriptor",
        detection: "Optional[UE4SSResult]",
    ) -> None:
        if not detection or not detection.mods_dir:
            raise RuntimeError("UE4SS mods directory not detected")
        components = content.components.types if content.components else ["lua"]
        bp_pak_files = content.components.bp_pak_files if content.components else []
        folder_name = content.folder_name
        t0 = time.monotonic()

        try:
            if any(c in components for c in ("lua", "cpp")):
                dest = detection.mods_dir / folder_name
                self._host.log(
                    f"[deploy] Deploying {content.content_type} '{folder_name}' "
                    f"from {cache_path} \u2192 {dest}"
                )
                if dest.exists():
                    shutil.rmtree(str(dest))
                    self._host.log(f"[deploy] Removed existing install at {dest}")
                # K-7: exclude .apf_cache; K-8 Fix B: exclude ue4ss.json
                shutil.copytree(
                    str(cache_path), str(dest),
                    ignore=shutil.ignore_patterns("enabled.txt", ".apf_cache", "ue4ss.json"),
                )
                n_files = sum(1 for _ in dest.rglob("*") if _.is_file())
                self._host.log(f"[deploy] Copied mod tree \u2192 {dest}  ({n_files} files)")
                with self._lock:
                    if self._mods_txt:
                        self._mods_txt.ensure_entry(folder_name, enabled=True)
                        self._mods_txt.save()
                        self._host.log(f"[deploy] mods.txt updated for '{folder_name}'")

            if "blueprint" in components and bp_pak_files:
                lm_dir = detection.logicmods_dir
                if lm_dir:
                    lm_dir.mkdir(parents=True, exist_ok=True)
                    lm_src = cache_path / "LogicMods"
                    for pak in bp_pak_files:
                        src_pak = lm_src / pak
                        if src_pak.exists():
                            shutil.copy2(str(src_pak), str(lm_dir / pak))
                            self._host.log(f"[deploy] Copied pak '{pak}' \u2192 {lm_dir}")

            elapsed = time.monotonic() - t0
            self._host.log(f"[deploy] DONE '{folder_name}' ({elapsed:.2f}s)")
        except Exception as exc:
            self._host.log(f"[deploy] ERROR deploying '{folder_name}': {exc}")
            raise

    def _deploy_template_content(self, cache_path: "Path", content: "TemplateDescriptor") -> None:
        game_name = content.game_id or content.name or ""
        target = self.get_templates_dir(game_name)
        if not target:
            raise RuntimeError("Cannot deploy template: framework mod not found or in conflict state")
        template_path = getattr(content, "template_path", game_name)
        self._host.log(f"[deploy] Deploying template '{template_path}' \u2192 {target}")
        try:
            target.mkdir(parents=True, exist_ok=True)
            n = 0
            for src in cache_path.rglob("*"):
                if src.is_dir():
                    continue
                rel = src.relative_to(cache_path)
                dst = target / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                n += 1
            self._host.log(f"[deploy] Template deployed ({n} files copied)")
        except Exception as exc:
            self._host.log(f"[deploy] ERROR deploying template '{template_path}': {exc}")
            raise

    def _deploy_binary_content(
        self,
        cache_path: "Path",
        content: "BinaryDescriptor",
        detection: "Optional[UE4SSResult]",
    ) -> None:
        platform_dir = getattr(detection, "platform_dir", None)
        if not detection or platform_dir is None or not platform_dir.parts:
            raise RuntimeError("Game platform directory not detected")
        import zipfile
        dest_dir = platform_dir
        install_type = getattr(content, "install_type", "")
        self._host.log(
            f"[deploy] Deploying binary '{content.name}' install_type={install_type} "
            f"from {cache_path}"
        )
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            zips = sorted(cache_path.glob("*.zip"))
            if zips:
                for zip_path in zips:
                    if zip_path.stem.lower() == "zmapgenbp":
                        mapgen_dir = dest_dir / "ue4ss" / "MapGenBP"
                        mapgen_dir.mkdir(parents=True, exist_ok=True)
                        self._host.log(
                            f"[deploy] Extracting {zip_path.name} as MapGenBP \u2192 {mapgen_dir}"
                        )
                        with zipfile.ZipFile(zip_path, "r") as zf:
                            zf.extractall(str(mapgen_dir))
                        continue
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        kind = _classify_zip(zf)
                        if kind == "blueprint_pak":
                            lm_dir = getattr(detection, "logicmods_dir", None)
                            if lm_dir and lm_dir.parts:
                                lm_dir.mkdir(parents=True, exist_ok=True)
                                self._host.log(
                                    f"[deploy] Extracting {zip_path.name} as {kind} \u2192 {lm_dir}"
                                )
                                for info in zf.infolist():
                                    if info.filename.lower().endswith(".pak"):
                                        zf.extract(info, str(lm_dir))
                            else:
                                self._host.log(
                                    f"[deploy] Extracting {zip_path.name} as {kind} \u2192 {dest_dir}"
                                )
                                zf.extractall(str(dest_dir))
                        elif kind == "unknown":
                            self._host.log(
                                f"[deploy] Skipped '{zip_path.name}': unknown zip layout — "
                                "manual installation required"
                            )
                        else:
                            self._host.log(
                                f"[deploy] Extracting {zip_path.name} as {kind} \u2192 {dest_dir}"
                            )
                            zf.extractall(str(dest_dir))
            else:
                for f in cache_path.iterdir():
                    if f.is_file() and f.suffix.lower() in (".dll", ".exe", ".pdb"):
                        shutil.copy2(str(f), str(dest_dir / f.name))
            self._host.log(f"[deploy] DONE binary '{content.name}'")
        except Exception as exc:
            self._host.log(f"[deploy] ERROR deploying binary '{content.name}': {exc}")
            raise

    def undeploy_content(
        self,
        record: "InstallRecord",
        detection: "Optional[UE4SSResult]",
    ) -> None:
        """Content-aware uninstall. Routes by content_type from InstallRecord."""
        if record.content_type in ("ap_mod", "third_party_mod", "framework_mod"):
            self._undeploy_mod_record(record, detection)
        elif record.content_type == "template":
            self._undeploy_template_record(record)
        elif record.content_type in ("github_release_binary", "external_url_binary", "manual_binary"):
            self._undeploy_binary_record(record, detection)

        if self._profile:
            from ..shared.data.install_state import InstallStateManager
            key = record.folder_name or record.name
            if key:
                InstallStateManager(self._profile.game_id).remove(key)

    def _undeploy_mod_record(
        self,
        record: "InstallRecord",
        detection: "Optional[UE4SSResult]",
    ) -> None:
        if not detection:
            return
        components = record.components or ["lua"]
        if any(c in components for c in ("lua", "cpp")):
            if detection.mods_dir:
                folder_path = detection.mods_dir / record.folder_name
                shutil.rmtree(str(folder_path), ignore_errors=True)
            with self._lock:
                if self._mods_txt:
                    self._mods_txt.remove_entry(record.folder_name)
                    self._mods_txt.save()
        if "blueprint" in components and detection.logicmods_dir:
            for pak in (record.bp_pak_files_deployed or []):
                try:
                    (detection.logicmods_dir / pak).unlink(missing_ok=True)
                except Exception:
                    pass

    def _undeploy_template_record(self, record: "InstallRecord") -> None:
        target = self.get_templates_dir(record.game_id or record.name)
        if not target or not target.exists():
            return
        shutil.rmtree(str(target), ignore_errors=True)

    def _undeploy_binary_record(
        self,
        record: "InstallRecord",
        detection: "Optional[UE4SSResult]",
    ) -> None:
        self._host.log(
            f"[deploy] Uninstall of binary '{record.name}' (type={record.install_type}) "
            "requires manual removal — automatic binary uninstall is not supported."
        )

    def get_uninstall_impact(self, record: "InstallRecord") -> dict:
        """Return {affected_mods: list[InstallRecord], template_dirs_removed: list[str]}."""
        from ..shared.data.install_state import InstallStateManager
        from ..shared.data.pipeline_state import InstallRecord as _IR
        from ..utils.dependency_resolver import resolve_uninstall_cascade
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

    # -----------------------------------------------------------------------
    # Deploy / undeploy (legacy — kept for callers not yet migrated to Phase F)
    # -----------------------------------------------------------------------

    def undeploy_mod(self, mod_info: "ModInfo", detection: Optional["UE4SSResult"]) -> None:
        """
        Remove all deployed components for a mod from the install target.
        Does not touch the download cache. Does not remove dependency DLLs.
        """
        if not detection:
            return

        components = getattr(mod_info, "components", ["lua"])

        if any(c in components for c in ("lua", "cpp")):
            shutil.rmtree(str(mod_info.folder_path), ignore_errors=True)
            with self._lock:
                if self._mods_txt:
                    self._mods_txt.remove_entry(mod_info.folder_name)
                    self._mods_txt.save()

        if "blueprint" in components and detection.logicmods_dir:
            for pak in getattr(mod_info, "bp_pak_files", []):
                pak_path = detection.logicmods_dir / pak
                try:
                    pak_path.unlink(missing_ok=True)
                except Exception:
                    pass

        if self._profile:
            from ..shared.data.install_state import InstallStateManager
            InstallStateManager(self._profile.game_id).remove(mod_info.folder_name)

    def deploy_mod(
        self,
        cache_path: "Path",
        folder_name: str,
        components: list,
        bp_pak_files: list,
        detection: "Optional[UE4SSResult]",
        game_id: str = "",
        metadata: "Optional[dict]" = None,
    ) -> None:
        """Copy cached mod to mods_dir, register in mods.txt, save install state."""
        if not detection or not detection.mods_dir:
            raise RuntimeError("UE4SS mods directory not detected")
        if any(c in components for c in ("lua", "cpp")):
            dest = detection.mods_dir / folder_name
            if dest.exists():
                shutil.rmtree(str(dest))
            shutil.copytree(str(cache_path), str(dest),
                            ignore=shutil.ignore_patterns("enabled.txt"))
            with self._lock:
                if self._mods_txt:
                    self._mods_txt.ensure_entry(folder_name, enabled=True)
                    self._mods_txt.save()
        if "blueprint" in components and bp_pak_files:
            lm_dir = detection.logicmods_dir
            if lm_dir:
                lm_dir.mkdir(parents=True, exist_ok=True)
                lm_src = cache_path / "LogicMods"
                for pak in bp_pak_files:
                    src_pak = lm_src / pak
                    if src_pak.exists():
                        shutil.copy2(str(src_pak), str(lm_dir / pak))
        gid = game_id or (self._profile.game_id if self._profile else "")
        if gid and metadata:
            from ..shared.data.install_state import InstallStateManager
            from ..shared.data.pipeline_state import InstallRecord
            record = InstallRecord(
                content_type=metadata.get("content_type", "ap_mod"),
                name=metadata.get("name", folder_name),
                version=metadata.get("version", ""),
                game_id=gid,
                folder_name=folder_name,
                description=metadata.get("description", ""),
                author=metadata.get("author", ""),
                mod_id=metadata.get("mod_id", ""),
                source_registry_url=metadata.get("source_registry_url", ""),
                source_repo=metadata.get("source_repo", ""),
                source_folder=metadata.get("source_folder", folder_name),
                components=components,
                bp_pak_files_deployed=bp_pak_files,
                capabilities_includes=metadata.get("capabilities_includes", []),
            )
            InstallStateManager(gid).add_record(record)

    def deploy_other(
        self,
        cache_path: "Path",
        install_type: str,
        detection: "Optional[UE4SSResult]",
    ) -> None:
        """Deploy an Other-category item (UE4SS or framework binaries).

        Each selected zip is inspected by TOC to determine its install target:
          "ue4ss"          → extract to platform_dir (Binaries/<arch>/)
          "framework_bin"  → extract to platform_dir
          "blueprint_pak"  → copy .pak files to logicmods_dir (Content/Paks/LogicMods/)
          "unknown"        → extract to platform_dir (safe fallback)
        """
        platform_dir = getattr(detection, "platform_dir", None)
        if not detection or platform_dir is None or not platform_dir.parts:
            raise RuntimeError("Game platform directory not detected")
        import zipfile
        dest_dir = platform_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        zips = sorted(cache_path.glob("*.zip"))
        if zips:
            for zip_path in zips:
                # zMapGenBP: UE4SS tool for .usmap generation — root-level contents
                # go directly into ue4ss/MapGenBP/ (not platform_dir root)
                if zip_path.stem.lower() == "zmapgenbp":
                    mapgen_dir = dest_dir / "ue4ss" / "MapGenBP"
                    mapgen_dir.mkdir(parents=True, exist_ok=True)
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(str(mapgen_dir))
                    continue
                with zipfile.ZipFile(zip_path, "r") as zf:
                    kind = _classify_zip(zf)
                    if kind == "blueprint_pak":
                        lm_dir = getattr(detection, "logicmods_dir", None)
                        if lm_dir and lm_dir.parts:
                            lm_dir.mkdir(parents=True, exist_ok=True)
                            for info in zf.infolist():
                                if info.filename.lower().endswith(".pak"):
                                    zf.extract(info, str(lm_dir))
                        else:
                            zf.extractall(str(dest_dir))
                    elif kind == "unknown":
                        self._host.log(
                            f"[deploy] Skipped '{zip_path.name}': unknown zip layout — "
                            "manual installation required (destination picker coming in a future update)"
                        )
                    else:
                        zf.extractall(str(dest_dir))
        else:
            for f in cache_path.iterdir():
                if f.is_file() and f.suffix.lower() in (".dll", ".exe", ".pdb"):
                    shutil.copy2(str(f), str(dest_dir / f.name))

    # -----------------------------------------------------------------------
    # Template deployment
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
            except Exception:
                pass
        # Prune empty directories left behind
        for dirpath in sorted(target.rglob("*"), reverse=True):
            if dirpath.is_dir():
                try:
                    dirpath.rmdir()
                except OSError:
                    pass

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

    # -----------------------------------------------------------------------
    # Framework mod cascade analysis
    # -----------------------------------------------------------------------

    def get_framework_uninstall_impact(self) -> dict:
        """
        Analyse the cascading damage caused by uninstalling the framework mod.

        Returns:
          {
            "affected_mods": [ModInfo, ...],    # installed AP mods with capabilities.include
            "template_dirs_removed": [Path, ...] # Template subdirs that would be deleted
          }

        Scans all installed AP mods for capabilities.include entries.  Any mod
        that has at least one include path is affected — its includes resolve
        into the framework mod's Templates/logic/ tree, which is removed with
        the framework mod.
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
            includes = getattr(mod, "capabilities_includes", [])
            if includes:
                affected.append(mod)

        return {
            "affected_mods": affected,
            "template_dirs_removed": template_dirs,
        }

    def get_component_status(self, mod_info: "ModInfo", detection: Optional["UE4SSResult"]) -> dict:
        """
        Return per-component presence status for a deployed mod.
        Keys: "lua", "cpp", "blueprint" — values: bool.
        """
        if not detection:
            return {}

        components = getattr(mod_info, "components", ["lua"])
        bp_pak_files = getattr(mod_info, "bp_pak_files", [])
        status = {}

        if "lua" in components:
            status["lua"] = (
                detection.mods_dir / mod_info.folder_name / "scripts" / "main.lua"
            ).exists()

        if "cpp" in components:
            status["cpp"] = (
                detection.mods_dir / mod_info.folder_name / "dlls" / "main.dll"
            ).exists()

        if "blueprint" in components:
            if bp_pak_files and detection.logicmods_dir:
                status["blueprint"] = all(
                    (detection.logicmods_dir / f).exists() for f in bp_pak_files
                )
            else:
                status["blueprint"] = False

        return status
