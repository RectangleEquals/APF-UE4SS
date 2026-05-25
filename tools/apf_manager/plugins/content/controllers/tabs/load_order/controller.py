"""
LoadOrderController — topo sort, dep info, and mods.txt writes for Tab 5.

Handles all service interactions so LoadOrderTab view never imports services directly.
"""
from __future__ import annotations

from typing import Optional, Tuple

from ......core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)


def _get_dep_info(mod, mod_by_id: dict) -> Tuple[str, str]:
    """Return (status, label) — status is 'error', 'warn', or 'ok'."""
    missing, incompat = [], []
    for dep_str in (mod.depends or []):
        dep_id = dep_str.split(" ")[0].strip()
        if dep_id not in mod_by_id:
            short = dep_id.split(".")[-1] if "." in dep_id else dep_id
            missing.append(short)
    for dep_str in (mod.incompatible or []):
        dep_id = dep_str.split(" ")[0].strip()
        if dep_id in mod_by_id:
            short = dep_id.split(".")[-1] if "." in dep_id else dep_id
            incompat.append(short)
    if missing:
        return "error", f"Missing: {', '.join(missing)}"
    if incompat:
        return "error", f"Conflicts: {', '.join(incompat)}"
    return "ok", ""


def _topo_sort_ap_mods(ap_mods: list, id_to_folder: dict) -> list:
    """Topological sort: framework first, then other AP mods in dependency order."""
    from ....controllers.mods.service import _FRAMEWORK_MOD_RE
    fw   = [m for m in ap_mods if m.mod_id and _FRAMEWORK_MOD_RE.match(m.mod_id)]
    rest = [m for m in ap_mods if m not in fw]

    folder_deps: dict = {}
    for m in rest:
        deps: set = set()
        for dep_str in (m.depends or []):
            dep_id = dep_str.split(" ")[0].strip()
            df = id_to_folder.get(dep_id)
            if df:
                deps.add(df)
        folder_deps[m.folder_name] = deps

    resolved: set = {m.folder_name for m in fw}
    result   = list(fw)
    remaining = list(rest)

    for _ in range(len(rest) + 1):
        if not remaining:
            break
        for mod in list(remaining):
            if folder_deps[mod.folder_name].issubset(resolved):
                result.append(mod)
                resolved.add(mod.folder_name)
                remaining.remove(mod)
                break
        else:
            result.extend(remaining)
            break
    return result


class LoadOrderController:
    """Non-Kivy controller for LoadOrderTab."""

    def __init__(self, host) -> None:
        self._host = host

    # -----------------------------------------------------------------------
    # Data access
    # -----------------------------------------------------------------------

    def get_mods_txt(self):
        deploy_svc = self._deploy_svc()
        return deploy_svc.mods_txt if deploy_svc else None

    def get_game_id_slug(self, profile=None) -> str:
        """Return the human-readable game ID slug for install state lookups."""
        from ...utils import slug_game_id
        _reg = (self._host.get_service("registry")
                if self._host.has_service("registry") else None)
        return slug_game_id(profile, _reg)

    def scan_mods(self) -> list:
        mods_svc = self._host.get_service("mods")
        return mods_svc.scan() if mods_svc else []

    def rescan_mods(self) -> list:
        mods_svc = self._host.get_service("mods")
        return mods_svc.rescan() if mods_svc else []

    # -----------------------------------------------------------------------
    # Dependency analysis
    # -----------------------------------------------------------------------

    def get_dep_info(self, mod, mod_by_id: dict) -> Tuple[str, str]:
        return _get_dep_info(mod, mod_by_id)

    def topo_sort_ap_mods(self, ap_mods: list, id_to_folder: dict) -> list:
        return _topo_sort_ap_mods(ap_mods, id_to_folder)

    # -----------------------------------------------------------------------
    # Load order mutations
    # -----------------------------------------------------------------------

    def set_enabled(self, folder_name: str, enabled: bool) -> None:
        deploy_svc = self._deploy_svc()
        if deploy_svc:
            deploy_svc.set_enabled(folder_name, enabled)
            self._host.notify_state_change("install")

    def reorder(self, folder_name: str, new_index: int) -> None:
        deploy_svc = self._deploy_svc()
        if deploy_svc:
            deploy_svc.reorder(folder_name, new_index)

    def fix_load_order(self, detection) -> None:
        """Sort AP mods by dependency constraints and write to mods.txt."""
        deploy_svc = self._deploy_svc()
        mods_svc = self._host.get_service("mods")
        if not deploy_svc or not mods_svc:
            return
        all_mods = mods_svc.scan()
        ap_mods = [m for m in all_mods if m.is_ap_mod]
        id_to_folder = {m.mod_id: m.folder_name for m in ap_mods if m.mod_id}
        sorted_mods = _topo_sort_ap_mods(ap_mods, id_to_folder)

        mods_txt = deploy_svc.mods_txt
        if not mods_txt:
            return

        order = mods_txt.get_order()
        non_ap = [n for n in order if n not in {m.folder_name for m in ap_mods}]
        new_order = [m.folder_name for m in sorted_mods] + non_ap

        try:
            mods_txt.reorder(new_order)
            mods_txt.save()
        except Exception as exc:
            logger.warning(f"fix_load_order save failed: {exc}")

    # -----------------------------------------------------------------------
    # BP Logic Mods section
    # -----------------------------------------------------------------------

    def get_bp_mods(self, detection, game_id: str = "") -> list:
        """
        Return all blueprint logic mods visible in the load order BP section.

        Each entry is a tuple of (name: str, bp_mods: list[BpLogicMod], is_managed: bool).
        Managed entries come from InstallStateManager records that include "blueprint" in
        their components. Unmanaged entries are orphan files found in LogicMods/ that are
        not tracked by any install record.
        """
        from ....models.state.install import InstallStateManager
        from ....models.state.pipeline import InstallRecord
        from ....models.descriptors.bp_component import parse_bp_mods

        results = []
        managed_pak_names: set[str] = set()

        if game_id:
            try:
                state = InstallStateManager(game_id)
                for d in state.get_all():
                    record = InstallRecord.from_dict(d)
                    if "blueprint" not in (record.components or []):
                        continue
                    pak_files = record.bp_pak_files_deployed or []
                    if not pak_files:
                        continue
                    managed_pak_names.update(pak_files)
                    # Group files by subfolder prefix so parse_bp_mods() receives
                    # plain filenames (not "SubfolderName/file.pak" paths).
                    # Legacy flat paths (no "/") fall back to using folder_name.
                    subfolders: dict[str, list[str]] = {}
                    for pak in pak_files:
                        parts = pak.split("/", 1)
                        if len(parts) == 2:
                            subfolders.setdefault(parts[0], []).append(parts[1])
                        else:
                            subfolders.setdefault(record.folder_name or "", []).append(pak)
                    for sf_name, files in subfolders.items():
                        bp_list = parse_bp_mods(files) or []
                        if bp_list:
                            display = sf_name or record.name or record.folder_name or ""
                            results.append((display, bp_list, True))
            except Exception as exc:
                logger.warning(f"[load_order] get_bp_mods: failed to read install state: {exc}")

        # Orphan scan — files/dirs in LogicMods/ not tracked by any install record.
        # Grouped by top-level directory (each dir = one BP mod); flat root files follow
        # stem-matching. Directories are scanned recursively so nested pak files are found.
        logicmods_dir = (
            (detection.ue4ss.logicmods_dir if (detection and detection.ue4ss) else None)
            or (detection.game.content_paks_dir / "LogicMods"
                if (detection and detection.game and detection.game.content_paks_dir) else None)
        )
        if logicmods_dir and logicmods_dir.is_dir():
            # Derive managed top-level subfolder names from "SubfolderName/..." pak paths.
            managed_subfolders: set[str] = set()
            for p in managed_pak_names:
                parts = p.split("/", 1)
                if len(parts) == 2:
                    managed_subfolders.add(parts[0])

            # Flat orphan files directly at LogicMods/ root.
            orphan_flat = [
                f.name for f in sorted(logicmods_dir.iterdir())
                if f.is_file() and f.suffix.lower() in (".pak", ".ucas", ".utoc")
                and f.name not in managed_pak_names
            ]
            for bp_mod in (parse_bp_mods(orphan_flat) or []):
                results.append((bp_mod.primary_name, [bp_mod], False))

            # Orphaned top-level subdirectories: recursively find all pak files within.
            for subdir in sorted(logicmods_dir.iterdir()):
                if not subdir.is_dir() or subdir.name in managed_subfolders:
                    continue
                subdir_files = [
                    f.name for f in sorted(subdir.rglob("*"))
                    if f.is_file() and f.suffix.lower() in (".pak", ".ucas", ".utoc")
                ]
                if subdir_files:
                    for bp_mod in (parse_bp_mods(subdir_files) or []):
                        results.append((subdir.name, [bp_mod], False))

        return results

    def is_bpml_active(self) -> bool:
        """Return True if BPModLoaderMod is installed and enabled."""
        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return False
        for mod in mods_svc.scan():
            if mod.folder_name.lower() == "bpmodloadermod":
                mods_txt = self.get_mods_txt()
                if mods_txt:
                    return mods_txt.is_enabled(mod.folder_name)
                return True  # present but no mods.txt — assume active
        return False

    # -----------------------------------------------------------------------
    # Error count (for pipeline panel badge)
    # -----------------------------------------------------------------------

    def get_error_count(self, detection) -> int:
        if not detection or not detection.valid:
            return 0
        mods_svc = self._host.get_service("mods")
        if not mods_svc:
            return 0
        mods = mods_svc.scan()
        mod_by_id = {m.mod_id: m for m in mods if m.mod_id}
        return sum(1 for m in mods if m.is_ap_mod and _get_dep_info(m, mod_by_id)[0] == "error")

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _deploy_svc(self):
        return self._host.get_service("deploy")
