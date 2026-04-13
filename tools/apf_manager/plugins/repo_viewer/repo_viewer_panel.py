"""
RepoViewerPanel — service for the repo_viewer dialog contribution.

Opens a pywebview SPA window showing a dependency tree of a multi-content repo:
  - Mods (with score breakdown)
  - Templates (with vocab file list)
  - Documentation (renders inline)
  - Submodule repos (collapsible, same structure)
  - External sources (Nexus, CurseForge, Thunderstore — docs-only)

Users select what to add, then click "Add Selected".
Result is passed back via on_confirm(selected: list[DiscoveredMod]).

Uses the html_viewer output_file mechanism for cross-process result handoff.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost
    from ..mods.registry_resolver import DiscoveredMod, FolderTreeNode

_EXTERNAL_URL_PATTERNS = {
    "nexus":       "nexusmods.com",
    "curseforge":  "curseforge.com",
    "thunderstore": "thunderstore.io",
}

_SPA_PATH = Path(__file__).parent / "repo_viewer_spa.html"


def _detect_external_type(url: str) -> str:
    for label, pattern in _EXTERNAL_URL_PATTERNS.items():
        if pattern in url:
            return label
    return "external"


def _freshness_color(last_push_days: int) -> str:
    if last_push_days <= 30:
        return "#4caf50"   # green
    elif last_push_days <= 90:
        return "#ffb300"   # yellow
    return "#757575"       # grey


def _score_framework(mod: "DiscoveredMod", game_id: str) -> tuple[int, dict]:
    """Lightweight scoring for display purposes (no repo_meta available here)."""
    score = 0
    bd: dict = {}
    expected = f"archipelago.{game_id}.framework"
    if mod.mod_id == expected:
        score += 3
        bd["mod_id_match"] = 3
    folder_leaf = mod.folder.split("/")[-1] if mod.folder else ""
    if folder_leaf == "APFrameworkMod" or mod.repo == "APFrameworkMod":
        score += 2
        bd["naming_convention"] = 2
    if mod.ue4ss_info:
        score += 2
        bd["ue4ss_present"] = 2
    else:
        score -= 2
        bd["no_ue4ss"] = -2
    return score, bd


def _score_mod(mod: "DiscoveredMod", game_id: str) -> tuple[int, dict]:
    """Lightweight scoring for regular mods (no stars/push data available)."""
    score = 0
    bd: dict = {}
    parts = mod.mod_id.split(".")
    if len(parts) >= 3 and parts[0] == "archipelago" and parts[1] == game_id:
        score += 2
        bd["valid_mod_id"] = 2
    if mod.readme_url:
        score += 1
        bd["has_docs"] = 1
    if mod.ue4ss_info:
        score += 1
        bd["ue4ss_present"] = 1
    if mod.manifest.get("depends"):
        score += 1
        bd["has_deps"] = 1
    return score, bd


def _build_tree_nodes(
    mods: list["DiscoveredMod"],
    game_id: str,
    existing_mod_ids: Optional[set] = None,
) -> list[dict]:
    """
    Convert a flat list of DiscoveredMods into a tree structure for the SPA.
    Groups by repo, deduplicates template paths, and nests submodule repos
    under their parent repos.
    """
    # Group by owner/repo
    by_repo: dict[str, list["DiscoveredMod"]] = {}
    for mod in mods:
        key = f"{mod.owner}/{mod.repo}"
        by_repo.setdefault(key, []).append(mod)

    nodes_map: dict[str, dict] = {}
    for repo_key, repo_mods in by_repo.items():
        children: list[dict] = []

        # One docs node per repo (README at repo root), placed first.
        repo_readme_url = next((m.readme_url for m in repo_mods if m.readme_url), None)
        if repo_readme_url:
            children.append({
                "type": "docs",
                "id": f"docs:{repo_key}:root",
                "label": "README",
                "readme_url": repo_readme_url,
                "selectable": False,
                "checked": False,
            })

        seen_tpaths: set[str] = set()
        for mod in repo_mods:
            if mod.external_source_url:
                ext_type = _detect_external_type(mod.external_source_url)
                children.append({
                    "type": "external",
                    "id": f"ext:{mod.owner}/{mod.repo}:{mod.folder}",
                    "label": mod.manifest.get("name") or mod.folder or repo_key,
                    "external_url": mod.external_source_url,
                    "external_type": ext_type,
                    "selectable": False,
                    "checked": False,
                })
            elif mod.mod_id:
                is_fw = mod.mod_id.endswith(".framework")
                if is_fw:
                    score, bd = _score_framework(mod, game_id)
                else:
                    score, bd = _score_mod(mod, game_id)
                is_conflict = bool(existing_mod_ids and mod.mod_id in existing_mod_ids)
                children.append({
                    "type": "mod",
                    "id": f"mod:{mod.owner}/{mod.repo}:{mod.mod_id}",
                    "label": mod.manifest.get("name") or mod.mod_id,
                    "mod_id": mod.mod_id,
                    "owner": mod.owner,
                    "repo": mod.repo,
                    "folder": mod.folder,
                    "description": mod.manifest.get("description", ""),
                    "readme_url": mod.readme_url,
                    "is_framework": is_fw,
                    "score": score,
                    "score_breakdown": bd,
                    "ue4ss_present": bool(mod.ue4ss_info),
                    "conflict": is_conflict,
                    "selectable": True,
                    "checked": not is_conflict,
                })
            # Deduplicated template nodes per repo
            if mod.templates_paths:
                for tpath in mod.templates_paths:
                    if tpath in seen_tpaths:
                        continue
                    seen_tpaths.add(tpath)
                    game_dir = tpath.split("/")[-1] if "/" in tpath else tpath
                    children.append({
                        "type": "template",
                        "id": f"tpl:{mod.owner}/{mod.repo}:{tpath}",
                        "label": f"Templates / {game_dir}",
                        "owner": mod.owner,
                        "repo": mod.repo,
                        "path": tpath,
                        "game_dir": game_dir,
                        "selectable": True,
                        "checked": game_dir.lower() == game_id.lower(),
                    })

        nodes_map[repo_key] = {
            "type": "repo",
            "id": f"repo:{repo_key}",
            "label": repo_key,
            "owner": repo_key.split("/")[0] if "/" in repo_key else "",
            "repo": repo_key.split("/")[1] if "/" in repo_key else repo_key,
            "children": children,
            "selectable": False,
            "checked": False,
        }

    # Nest submodule repos under their parent repos.
    top_level: list[dict] = []
    for repo_key, node in nodes_map.items():
        parent_key = next(
            (m.submodule_of for m in by_repo[repo_key] if m.submodule_of), None
        )
        if parent_key and parent_key in nodes_map:
            node["is_submodule"] = True
            nodes_map[parent_key]["children"].append(node)
        else:
            top_level.append(node)

    return top_level


def _folder_tree_to_spa_nodes(tree: "FolderTreeNode") -> list[dict]:
    """
    Convert a FolderTreeNode hierarchy into the SPA-ready JSON tree.
    The root node becomes the single top-level item in the list.
    """
    def _convert(node: "FolderTreeNode", depth: int) -> dict:
        ntype = node.node_type
        # Map internal types to SPA types
        if ntype == "root":
            spa_type = "repo"
        elif ntype == "submodule":
            spa_type = "repo"
        elif ntype == "mod_dir":
            spa_type = "mod"
        elif ntype == "template_dir":
            spa_type = "template"
        elif ntype == "file":
            spa_type = "docs"
        elif ntype == "lua_dir":
            spa_type = "lua_dir"
        elif ntype == "cpp_dir":
            spa_type = "cpp_dir"
        elif ntype == "bp_dir":
            spa_type = "bp_dir"
        else:
            spa_type = "dir"

        node_id = f"{spa_type}:{node.owner}/{node.repo}:{node.path}"

        base: dict = {
            "type": spa_type,
            "id": node_id,
            "label": node.name,
            "owner": node.owner,
            "repo": node.repo,
            "path": node.path,
            "is_submodule": (ntype == "submodule"),
            "game_id_match": node.game_id_match,
            "conflict": node.conflict,
            "selectable": False,
            "checked": False,
            "disabled": not node.game_id_match,
        }

        if spa_type == "docs":
            base["download_url"] = node.download_url
            base["readme_url"] = node.download_url  # keep compat

        elif spa_type == "mod" and node.mod:
            m = node.mod
            is_fw = m.mod_id.endswith(".framework")
            if is_fw:
                score, bd = _score_framework(m, m.mod_id.split(".")[1] if len(m.mod_id.split(".")) >= 2 else "")
            else:
                game_part = m.mod_id.split(".")[1] if len(m.mod_id.split(".")) >= 2 else ""
                score, bd = _score_mod(m, game_part)
            base.update({
                "mod_id": m.mod_id,
                "folder": m.folder,
                "description": m.manifest.get("description", ""),
                "version": m.manifest.get("version", ""),
                "readme_url": m.readme_url,
                "is_framework": is_fw,
                "score": score,
                "score_breakdown": bd,
                "ue4ss_present": bool(m.ue4ss_info),
                "ue4ss_info": m.ue4ss_info or {},
                "components": getattr(m, "components", ["lua"]),
                "bp_pak_files": getattr(m, "bp_pak_files", []),
                "selectable": node.game_id_match and not node.conflict,
                "checked": node.game_id_match and not node.conflict,
                "disabled": not node.game_id_match,
            })

        elif spa_type == "template":
            game_dir = node.name
            base.update({
                "game_dir": game_dir,
                "selectable": node.game_id_match,
                "checked": node.game_id_match and not node.conflict,
                "disabled": not node.game_id_match,
            })

        elif spa_type == "lua_dir":
            base.update({"component_label": "Lua scripts"})
        elif spa_type == "cpp_dir":
            base.update({"component_label": "C++ module"})
        elif spa_type == "bp_dir":
            base.update({"component_label": "Blueprint Logic Mod"})

        # Children
        if node.children:
            base["children"] = [_convert(c, depth + 1) for c in node.children]

        return base

    return [_convert(tree, 0)]


class RepoViewerPanel:
    """
    Service for the repo_viewer dialog.
    Registered as "repo_viewer" by __init__.py.
    """

    def __init__(self, host: "PluginHost") -> None:
        self._host = host

    def show(
        self,
        repo_url: str = "",
        game_id: str = "",
        traversal_result: Optional[list] = None,
        folder_tree: Optional["FolderTreeNode"] = None,
        existing_mod_ids: Optional[set] = None,
        on_confirm: Optional[Callable[[list], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Open the Repo Viewer SPA window.

        repo_url          — display URL for the title bar
        game_id           — current game ID for filtering/scoring
        traversal_result  — pre-fetched list[DiscoveredMod] (for fallback and result lookup)
        folder_tree       — FolderTreeNode root (preferred; shows real folder structure)
        on_confirm        — called with list[DiscoveredMod] of selected items when user confirms
        on_cancel         — called if user cancels / closes without confirming
        """
        viewer = self._html_viewer()
        if viewer is None:
            self._host.log("[repo_viewer] html_viewer service not available")
            if on_cancel:
                on_cancel()
            return

        mods = traversal_result or []
        if folder_tree is not None:
            nodes = _folder_tree_to_spa_nodes(folder_tree)
        else:
            nodes = _build_tree_nodes(mods, game_id, existing_mod_ids)

        # Build id → DiscoveredMod lookup for result construction.
        # When folder_tree is used, mod node IDs are "mod:{owner}/{repo}:{folder_path}".
        # Fallback: legacy flat IDs "mod:{owner}/{repo}:{mod_id}" and "tpl:...".
        id_to_mod: dict[str, "DiscoveredMod"] = {}
        if folder_tree is not None:
            # Walk the SPA nodes to build the lookup
            def _walk_nodes(node_list):
                for n in node_list:
                    if n.get("type") == "mod" and n.get("mod_id"):
                        # We need to recover the DiscoveredMod — find it from flat mods list
                        mid = n["mod_id"]
                        matched = next((m for m in mods if m.mod_id == mid), None)
                        if matched:
                            id_to_mod[n["id"]] = matched
                    if n.get("children"):
                        _walk_nodes(n["children"])
            _walk_nodes(nodes)
        else:
            for mod in mods:
                if mod.mod_id:
                    id_to_mod[f"mod:{mod.owner}/{mod.repo}:{mod.mod_id}"] = mod
                for tpath in mod.templates_paths:
                    id_to_mod[f"tpl:{mod.owner}/{mod.repo}:{tpath}"] = mod

        # Build SPA HTML
        tree_json = json.dumps(nodes, ensure_ascii=False).replace("</", "<\\/")
        game_id_json = json.dumps(game_id, ensure_ascii=False)
        repo_url_json = json.dumps(repo_url, ensure_ascii=False)

        try:
            spa_template = _SPA_PATH.read_text(encoding="utf-8")
        except Exception as exc:
            self._host.log(f"[repo_viewer] Could not read SPA template: {exc}")
            if on_cancel:
                on_cancel()
            return

        spa_html = spa_template.replace(
            "/*__TREE_JSON__*/", tree_json
        ).replace(
            "/*__GAME_ID__*/", game_id_json
        ).replace(
            "/*__REPO_URL__*/", repo_url_json
        )

        # Temp file for result handoff
        tmp_fd, output_file = tempfile.mkstemp(suffix=".json", prefix="repo_viewer_")
        os.close(tmp_fd)
        # Seed with empty/cancel sentinel
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump({"action": "cancel", "selected": []}, f)
        except Exception:
            pass

        label = repo_url or "Review Repository"

        def _on_closed():
            # Read result written by pywebview.api.confirm()
            result = {"action": "cancel", "selected": []}
            try:
                with open(output_file, encoding="utf-8") as f:
                    result = json.load(f)
            except Exception:
                pass
            try:
                os.unlink(output_file)
            except OSError:
                pass

            if result.get("action") == "confirm":
                selected_ids: list[str] = result.get("selected", [])
                selected_mods = [
                    id_to_mod[sid] for sid in selected_ids if sid in id_to_mod
                ]
                # Deduplicate
                seen = set()
                deduped = []
                for m in selected_mods:
                    key = (m.owner, m.repo, m.mod_id)
                    if key not in seen:
                        seen.add(key)
                        deduped.append(m)
                if on_confirm:
                    on_confirm(deduped)
            else:
                if on_cancel:
                    on_cancel()

        viewer.show(
            label,
            spa_html,
            width=1200,
            height=800,
            inject_titlebar=False,
            on_closed=_on_closed,
            output_file=output_file,
        )

    def _html_viewer(self):
        if self._host.has_service("html_viewer"):
            return self._host.get_service("html_viewer")
        return None
