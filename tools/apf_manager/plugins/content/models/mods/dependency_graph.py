"""
dependency_graph.py — typed dependency graph utilities.

Used by Content tab (pre-queue validation) and Downloads tab (install ordering).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..descriptors.base import ContentDescriptor
    from ..state.pipeline import InstallRecord


def resolve_install_order(
    staged: list,
    available: dict,
    installed: dict,
) -> tuple:
    """Topological sort of staged ContentDescriptors by dependency graph.

    Parameters
    ----------
    staged    : list[ContentDescriptor] — items the user wants to queue/install
    available : dict[str, ContentDescriptor] — mod_id → descriptor from registry
    installed : dict[str, InstallRecord] — mod_id → install record from InstallStateManager

    Returns
    -------
    (ordered, missing, warnings)
        ordered  : list[ContentDescriptor] in safe install order
                   (Other → Framework → AP mods topo-sorted → ThirdParty → Templates)
        missing  : list[str] mod_ids that are hard deps absent from staged + installed
        warnings : list[str] human-readable incompatibility / constraint warnings
    """
    from ..descriptors.types import (
        BinaryDescriptor, FrameworkModDescriptor, APModDescriptor,
        ThirdPartyModDescriptor, TemplateDescriptor, ModDescriptor,
    )
    from ..descriptors.base import DependencySpec

    other_items:   list = []
    fw_mods:       list = []
    ap_mods:       list = []
    tp_mods:       list = []
    templates:     list = []

    for item in staged:
        if isinstance(item, BinaryDescriptor):
            other_items.append(item)
        elif isinstance(item, FrameworkModDescriptor):
            fw_mods.append(item)
        elif isinstance(item, APModDescriptor):
            ap_mods.append(item)
        elif isinstance(item, ThirdPartyModDescriptor):
            tp_mods.append(item)
        elif isinstance(item, TemplateDescriptor):
            templates.append(item)
        elif isinstance(item, ModDescriptor):
            tp_mods.append(item)

    # Build staged mod_id set for dep checking
    staged_ids: set = set()
    for item in staged:
        mid = getattr(item, "mod_id", "")
        if mid:
            staged_ids.add(mid)

    missing:  list[str] = []
    warnings: list[str] = []

    # Validate deps for each AP mod
    for mod in ap_mods + fw_mods:
        for dep in (mod.dependencies or []):
            if not isinstance(dep, DependencySpec):
                continue
            dep_id = dep.mod_id
            if not dep_id:
                continue
            if dep.is_incompatible:
                if dep_id in installed:
                    warnings.append(f"{mod.name} conflicts with installed mod '{dep_id}'")
            else:
                if dep_id not in staged_ids and dep_id not in installed and dep_id not in available:
                    missing.append(dep_id)

    # Topological sort of AP mods (framework first, then by dep order)
    id_to_mod = {m.mod_id: m for m in ap_mods if m.mod_id}

    # Build dep graph: mod_id → set of mod_ids it depends on (within staged AP mods)
    dep_graph: dict = {m.mod_id: set() for m in ap_mods if m.mod_id}
    for mod in ap_mods:
        mid = mod.mod_id
        if not mid:
            continue
        for dep in (mod.dependencies or []):
            if not isinstance(dep, DependencySpec) or dep.is_incompatible:
                continue
            if dep.mod_id in id_to_mod:
                dep_graph[mid].add(dep.mod_id)

    sorted_ap = _kahn_sort(ap_mods, dep_graph)

    ordered = other_items + fw_mods + sorted_ap + tp_mods + templates
    return ordered, missing, warnings


def _kahn_sort(mods: list, dep_graph: dict) -> list:
    """Kahn's topological sort on a list of mods given a dep_graph of mod_id → {dep_mod_ids}."""
    remaining = list(mods)
    resolved_ids: set = set()
    result: list = []

    for _ in range(len(mods) + 1):
        if not remaining:
            break
        for mod in list(remaining):
            mid = mod.mod_id
            deps = dep_graph.get(mid, set())
            if deps.issubset(resolved_ids):
                result.append(mod)
                if mid:
                    resolved_ids.add(mid)
                remaining.remove(mod)
                break
        else:
            # Cycle or unresolvable — append remainder as-is
            result.extend(remaining)
            break
    return result


def resolve_uninstall_cascade(
    target: "InstallRecord",
    all_installed: list,
) -> list:
    """Return all InstallRecords that depend (directly or transitively) on target.

    Returns in reverse-dependency order: leaves (most-dependent) first,
    safe for sequential uninstall.
    """
    target_id = target.mod_id or target.folder_name
    if not target_id:
        return []

    def _directly_depends(record, on_id: str, is_framework: bool) -> bool:
        if record.folder_name == target.folder_name:
            return False
        if is_framework and record.capabilities_includes:
            return True
        if on_id and on_id in (record.dependencies or []):
            return True
        return any(on_id in inc for inc in (record.capabilities_includes or []))

    is_fw = target.content_type == "framework_mod"

    # BFS to collect transitive cascade
    visited: set[str] = {target.folder_name}
    queue = [r for r in all_installed if _directly_depends(r, target_id, is_fw)]
    result: list = []

    while queue:
        dep = queue.pop(0)
        if dep.folder_name in visited:
            continue
        visited.add(dep.folder_name)
        result.append(dep)
        # Transitive: find things that depend on this dep
        sub_id = dep.mod_id or dep.folder_name
        sub_fw = dep.content_type == "framework_mod"
        for r in all_installed:
            if r.folder_name not in visited and _directly_depends(r, sub_id, sub_fw):
                queue.append(r)

    # Reverse: leaves (most-dependent) first so uninstalling in this order is safe
    result.reverse()
    return result
