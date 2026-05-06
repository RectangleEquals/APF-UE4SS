"""DeployContentMixin — deploy/undeploy logic for DeployService."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ......core.ue4ss import UE4SSResult
    from ....models.descriptors.base import ContentDescriptor
    from ....models.state.pipeline import InstallRecord


class DeployContentMixin:
    """Mixin for DeployService: deploy_content, undeploy_content, and zip dispatch."""

    # -----------------------------------------------------------------------
    # Typed deploy / undeploy
    # -----------------------------------------------------------------------

    def deploy_content(
        self,
        cache_path: "Path",
        content: "ContentDescriptor",
        detection: "Optional[UE4SSResult]",
        game_id: str = "",
    ) -> "InstallRecord":
        """Content-aware dispatch. Routes by content type, saves InstallRecord for mods."""
        from ....models.descriptors.types import ModDescriptor, TemplateDescriptor, BinaryDescriptor
        from ....models.state.pipeline import InstallRecord
        from ....models.state.install import InstallStateManager

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
        content,
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

    def _deploy_template_content(self, cache_path: "Path", content) -> None:
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

    # -----------------------------------------------------------------------
    # Zip controller dispatch
    # -----------------------------------------------------------------------

    @staticmethod
    def _zip_controller_classes():
        from ..ue4ss.zip import UE4SSZipFileController
        from ..framework.zip import FrameworkZipFileController
        from ..blueprint_pak.zip import BlueprintPakZipFileController
        return [UE4SSZipFileController, FrameworkZipFileController, BlueprintPakZipFileController]

    def _find_zip_controller(self, zip_path: "Path", content):
        """
        Open zip_path, try each registered controller in order, return the first
        that classifies it (layout stored as instance state). Returns None if
        no controller recognises the zip layout.
        """
        import zipfile
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for cls in self._zip_controller_classes():
                    ctrl = cls(content)
                    if ctrl.classify(zf):
                        return ctrl
        except zipfile.BadZipFile as exc:
            self._host.log(f"[deploy] WARN: corrupt zip '{zip_path.name}': {exc}")
        return None

    def _dispatch_zip(
        self,
        zip_path: "Path",
        content,
        dest_dir: "Path",
        logicmods_dir: "Optional[Path]",
    ) -> None:
        """
        Shared per-zip dispatch used by both _deploy_binary_content and deploy_other.

        MapGenBP zips are handled specially (fixed target). All other zips are
        routed to the appropriate install controller via _find_zip_controller.
        """
        import zipfile
        if zip_path.stem.lower() == "zmapgenbp":
            mapgen_dir = dest_dir / "ue4ss" / "MapGenBP"
            mapgen_dir.mkdir(parents=True, exist_ok=True)
            self._host.log(f"[deploy] Extracting {zip_path.name} as MapGenBP \u2192 {mapgen_dir}")
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(str(mapgen_dir))
            return
        ctrl = self._find_zip_controller(zip_path, content)
        if ctrl is None:
            self._host.log(
                f"[deploy] Skipped '{zip_path.name}': unknown zip layout — "
                "manual installation required"
            )
            return
        install_ctrl = ctrl.create_install_controller()
        self._host.log(
            f"[deploy] Extracting {zip_path.name} via "
            f"{type(install_ctrl).__name__} \u2192 {dest_dir}"
        )
        install_ctrl.deploy(zip_path, dest_dir, logicmods_dir=logicmods_dir)

    def _deploy_binary_content(
        self,
        cache_path: "Path",
        content,
        detection: "Optional[UE4SSResult]",
    ) -> None:
        platform_dir = getattr(detection, "platform_dir", None)
        if not detection or platform_dir is None or not platform_dir.parts:
            raise RuntimeError("Game platform directory not detected")
        dest_dir = platform_dir
        install_type = getattr(content, "install_type", "")
        logicmods_dir = getattr(detection, "logicmods_dir", None)
        self._host.log(
            f"[deploy] Deploying binary '{content.name}' install_type={install_type} "
            f"from {cache_path}"
        )
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            zips = sorted(cache_path.glob("*.zip"))
            if zips:
                for zip_path in zips:
                    self._dispatch_zip(zip_path, content, dest_dir, logicmods_dir)
            else:
                for f in cache_path.iterdir():
                    if f.is_file() and f.suffix.lower() in (".dll", ".exe", ".pdb"):
                        shutil.copy2(str(f), str(dest_dir / f.name))
            self._host.log(f"[deploy] DONE binary '{content.name}'")
        except Exception as exc:
            self._host.log(f"[deploy] ERROR deploying binary '{content.name}': {exc}")
            raise

    # -----------------------------------------------------------------------
    # Undeploy
    # -----------------------------------------------------------------------

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
            from ....models.state.install import InstallStateManager
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
                except Exception as exc:
                    self._host.log(f"[deploy] WARN: failed to remove pak '{pak}': {exc}")

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

    # -----------------------------------------------------------------------
    # Legacy deploy methods (kept for callers not yet migrated to Phase F)
    # -----------------------------------------------------------------------

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
            from ....models.state.install import InstallStateManager
            from ....models.state.pipeline import InstallRecord
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
        """Deploy an Other-category item (UE4SS or framework binaries)."""
        platform_dir = getattr(detection, "platform_dir", None)
        if not detection or platform_dir is None or not platform_dir.parts:
            raise RuntimeError("Game platform directory not detected")
        dest_dir = platform_dir
        logicmods_dir = getattr(detection, "logicmods_dir", None)
        dest_dir.mkdir(parents=True, exist_ok=True)
        zips = sorted(cache_path.glob("*.zip"))
        if zips:
            for zip_path in zips:
                self._dispatch_zip(zip_path, None, dest_dir, logicmods_dir)
        else:
            for f in cache_path.iterdir():
                if f.is_file() and f.suffix.lower() in (".dll", ".exe", ".pdb"):
                    shutil.copy2(str(f), str(dest_dir / f.name))

    def undeploy_mod(self, mod_info, detection: "Optional[UE4SSResult]") -> None:
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
                except Exception as exc:
                    self._host.log(f"[deploy] WARN: failed to remove pak '{pak}': {exc}")
        if self._profile:
            from ....models.state.install import InstallStateManager
            InstallStateManager(self._profile.game_id).remove(mod_info.folder_name)
