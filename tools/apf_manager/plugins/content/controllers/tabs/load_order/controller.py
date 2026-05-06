"""
LoadOrderController — topo sort, dep info, and mods.txt writes for Tab 5.

Handles all service interactions so LoadOrderTab view never imports services directly.
"""
from __future__ import annotations

from typing import Optional, Tuple


def _get_dep_info(mod, mod_by_id: dict) -> Tuple[str, str]:
    """Return (status, label) — status is 'error', 'warn', or 'ok'."""
    missing, incompat = [], []
    for dep_str in (getattr(mod, "depends", None) or []):
        dep_id = dep_str.split(" ")[0].strip()
        if dep_id not in mod_by_id:
            short = dep_id.split(".")[-1] if "." in dep_id else dep_id
            missing.append(short)
    for dep_str in (getattr(mod, "incompatible", None) or []):
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
        for dep_str in (getattr(m, "depends", None) or []):
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
            mods_txt.set_order(new_order)
            mods_txt.save()
        except Exception as exc:
            self._host.log(f"[load_order_ctrl] WARN: fix_load_order save failed: {exc}")

    # -----------------------------------------------------------------------
    # Error count (for pipeline panel badge)
    # -----------------------------------------------------------------------

    def get_error_count(self, detection) -> int:
        if not detection or not getattr(detection, "valid", False):
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
