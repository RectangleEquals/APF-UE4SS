"""
RegistryResolver — traversal, scoring, search, and blacklist for the mod registry.

Registry format:
  - A registry is any GitHub repo the app can resolve to ≥1 AP mod.
  - No mandatory descriptor. Everything inferred from structure:
      depth-1 subfolder containing manifest.json → mod
      Templates/<GameName>/ → template provider
      submodule entries in root listing → follow recursively (depth ≤ 3)
      ue4ss.json at repo root (framework mod repo only) → UE4SS options

Traversal uses the GitHub Contents API (no git clone required).
Per-repo GitHubAPI instances are created with the bundled PAT.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable

# Bundled PAT — use centralized path from github_api.py
from ...core.remote.github_api import _BUNDLED_TOKEN_PATH as _BUNDLED_PAT

# Blacklist is fetched from this repo's own source tree (never cached)
_BLACKLIST_OWNER = "RectangleEquals"
_BLACKLIST_REPO  = "APF-UE4SS"
_BLACKLIST_PATH  = "tools/apf_manager/data/blacklist.json"

_GITHUB_URL_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s.]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

_GITMODULES_PATH_RE  = re.compile(r'path\s*=\s*(.+)')
_GITMODULES_URL_RE   = re.compile(r'url\s*=\s*(.+)')
# Core framework mod ID pattern: archipelago.<game_id>.framework (exact match)
_FRAMEWORK_MOD_RE    = re.compile(r'^archipelago\.[^.]+\.framework$')


def _is_framework_mod_id(mod_id: str) -> bool:
    """Return True only for exact archipelago.<game>.framework pattern."""
    return bool(_FRAMEWORK_MOD_RE.match(mod_id or ""))


def _parse_gitmodules(text: str) -> dict[str, str]:
    """Parse .gitmodules text → {submodule_path: remote_url}."""
    result: dict[str, str] = {}
    current_path: Optional[str] = None
    for line in text.splitlines():
        line = line.strip()
        m = _GITMODULES_PATH_RE.match(line)
        if m:
            current_path = m.group(1).strip()
            continue
        m = _GITMODULES_URL_RE.match(line)
        if m and current_path:
            result[current_path] = m.group(1).strip()
            current_path = None
    return result


# ---------------------------------------------------------------------------
# DiscoveredMod — result of traversal
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredMod:
    owner: str
    repo: str
    folder: str          # subfolder path within the repo
    manifest: dict       # raw manifest.json content (may be synthetic {"name": folder_name} for non-AP)
    mod_id: str          # manifest["mod_id"] — empty string "" for non-AP mods
    readme_url: str = ""
    ue4ss_info: Optional[dict] = None      # parsed ue4ss.json (framework mod repos only)
    templates_paths: list = field(default_factory=list)  # e.g. ["Templates/Palworld"]
    external_source_url: str = ""          # Nexus/CurseForge/Thunderstore URL (docs-only)
    submodule_of: str = ""                 # "owner/repo" of the parent if from a submodule
    components: list = field(default_factory=lambda: ["lua"])
    bp_pak_files: list = field(default_factory=list)
    # BP-Combined: True when BP paks coexist with Lua/C++ in the same mod folder.
    # BP-Only (False): paks are standalone, install as their own content row.
    bp_is_combined: bool = False
    # All mods from the same registry repo share this slug for grouping in the pipeline.
    source_package_id: str = ""           # "{owner}/{repo}"
    # True when this mod's content came from a git submodule of the parent registry.
    is_submodule_content: bool = False


# ---------------------------------------------------------------------------
# FolderTreeNode — hierarchical repo tree for the Repo Viewer
# ---------------------------------------------------------------------------

@dataclass
class FolderTreeNode:
    """
    One node in the hierarchical folder tree shown by the Repo Viewer.
    node_type: "root" | "dir" | "mod_dir" | "non_ap_mod" | "template_dir"
               | "lua_dir" | "cpp_dir" | "bp_dir" | "file" | "submodule"
    """
    node_type: str
    name: str               # display name (no path prefix)
    path: str               # full path within repo (e.g. "APFrameworkMod/README.md")
    owner: str
    repo: str
    download_url: str = ""  # raw download URL (for file nodes)
    mod: Optional["DiscoveredMod"] = None   # set for mod_dir nodes
    submodule_url: str = ""                 # for submodule nodes
    game_id_match: bool = True              # False = wrong-game content
    conflict: bool = False                  # mod_id already in another registered registry
    children: list = field(default_factory=list)  # list[FolderTreeNode]


def parse_github_url(url: str) -> Optional[tuple[str, str]]:
    """Parse a GitHub URL → (owner, repo) or None if not a valid GitHub repo URL."""
    m = _GITHUB_URL_RE.match(url.strip().rstrip("/"))
    if m:
        return m.group("owner"), m.group("repo")
    return None


# ---------------------------------------------------------------------------
# RegistryResolver
# ---------------------------------------------------------------------------

class RegistryResolver:
    """Traversal, scoring, GitHub topic search, and blacklist management."""

    def __init__(self, on_status: Optional[Callable[[str, str], None]] = None) -> None:
        self._on_status = on_status or (lambda level, msg: None)
        self._blacklist_cache: Optional[set[str]] = None  # in-memory only, never persisted
        self._blacklist_cache_time: float = 0.0

    # -----------------------------------------------------------------------
    # Traversal
    # -----------------------------------------------------------------------

    def traverse(
        self,
        url: str,
        cache: "RegistryCache",
        visited: Optional[set] = None,
        depth: int = 0,
    ) -> list[DiscoveredMod]:
        """
        Recursively discover AP mods in a GitHub repo and its submodules.

        Depth limit: 3. Cycle detection via visited set (normalised owner/repo).
        Results are cached per repo for TTL_TRAVERSAL seconds.
        """
        from .registry_cache import TTL_TRAVERSAL

        if depth > 3:
            return []
        if visited is None:
            visited = set()

        parsed = parse_github_url(url)
        if not parsed:
            self._on_status("warn", f"Cannot parse GitHub URL: {url}")
            return []

        owner, repo = parsed
        norm_key = f"{owner.lower()}/{repo.lower()}"
        if norm_key in visited:
            return []
        visited.add(norm_key)

        # Check traversal cache
        cache_key = f"{owner}+{repo}/traversal.json"
        cached = cache.get(cache_key, TTL_TRAVERSAL)
        if cached:
            try:
                raw = json.loads(cached)
                return [
                    DiscoveredMod(
                        components=d.pop("components", ["lua"]),
                        bp_pak_files=d.pop("bp_pak_files", []),
                        bp_is_combined=d.pop("bp_is_combined", False),
                        source_package_id=d.pop("source_package_id", ""),
                        is_submodule_content=d.pop("is_submodule_content", False),
                        **d,
                    )
                    for d in raw
                ]
            except Exception:
                pass

        api = self._make_api(owner, repo)
        contents = api.list_contents("")
        if not contents:
            return []

        # Optional ue4ss.json at repo root (only meaningful for framework mod repos)
        ue4ss_info: Optional[dict] = None
        for entry in contents:
            if entry["name"] == "ue4ss.json" and entry.get("download_url"):
                raw_text = api.fetch_text(entry["download_url"])
                if raw_text:
                    try:
                        ue4ss_info = json.loads(raw_text)
                    except Exception:
                        pass
                break

        # UE4SS submodule: a submodule with no manifest.json treated as UE4SS source
        # (handled during submodule traversal — if a submodule yields no mods, check
        #  if its repo name suggests UE4SS and create a synthetic ue4ss entry)

        # Templates/<game>/ directories at repo root
        templates_paths: list[str] = []
        templates_dir = next(
            (e for e in contents if e["name"] == "Templates" and e["type"] == "dir"), None
        )
        if templates_dir:
            try:
                sub = api.list_contents("Templates")
                for game_dir in sub:
                    if game_dir["type"] == "dir":
                        templates_paths.append(f"Templates/{game_dir['name']}")
            except Exception:
                pass

        mods: list[DiscoveredMod] = []

        # Depth-1 subfolders — each is a candidate mod if it contains manifest.json
        for entry in contents:
            if entry["type"] != "dir":
                continue
            folder_path = entry["path"]
            try:
                sub_contents = api.list_contents(folder_path)
            except Exception:
                continue

            manifest_entry = next(
                (e for e in sub_contents if e["name"] == "manifest.json"), None
            )
            if not (manifest_entry and manifest_entry.get("download_url")):
                # No manifest.json — detect non-AP mods from directory structure alone.
                has_lua       = any(e["name"].lower() == "scripts"   and e["type"] == "dir" for e in sub_contents)
                has_cpp       = any(e["name"].lower() == "dlls"      and e["type"] == "dir" for e in sub_contents)
                has_logic_dir = any(e["name"].lower() == "logicmods" and e["type"] == "dir" for e in sub_contents)
                has_bp_paks   = any(e["name"].lower().endswith(".pak")                       for e in sub_contents)
                has_bp        = has_logic_dir or has_bp_paks
                bp_combined   = has_bp and (has_lua or has_cpp)
                if has_lua or has_cpp or has_bp:
                    folder_name = folder_path.split("/")[-1] if "/" in folder_path else folder_path
                    _comps   = (["lua"] if has_lua else []) + (["cpp"] if has_cpp else []) + (["blueprint"] if has_bp else [])
                    _bp_paks = [e["name"] for e in sub_contents if e["name"].lower().endswith(".pak")]
                    mods.append(DiscoveredMod(
                        owner=owner, repo=repo, folder=folder_path,
                        manifest={"name": folder_name},
                        mod_id="",
                        readme_url="", ue4ss_info=None, templates_paths=templates_paths,
                        components=_comps, bp_pak_files=_bp_paks,
                        bp_is_combined=bp_combined,
                        source_package_id=f"{owner}/{repo}",
                    ))
                continue

            manifest_text = api.fetch_text(manifest_entry["download_url"])
            if not manifest_text:
                continue
            try:
                manifest = json.loads(manifest_text)
            except Exception:
                continue

            mod_id = manifest.get("mod_id", "")

            readme_url = ""
            readme_entry = next(
                (e for e in sub_contents
                 if e["name"].lower() in ("readme.md", "readme.txt", "readme")),
                None,
            )
            if readme_entry and readme_entry.get("download_url"):
                readme_url = readme_entry["download_url"]

            # Attach ue4ss_info to the core framework mod in this repo.
            # Prefer root-level ue4ss.json; fall back to subfolder ue4ss.json (e.g. APFrameworkMod/).
            mod_ue4ss = ue4ss_info if _is_framework_mod_id(mod_id) else None
            if _is_framework_mod_id(mod_id) and not mod_ue4ss:
                _sub_ue4ss_e = next(
                    (e for e in sub_contents
                     if e.get("name") == "ue4ss.json" and e.get("download_url")),
                    None,
                )
                if _sub_ue4ss_e:
                    _ue4ss_text = api.fetch_text(_sub_ue4ss_e["download_url"])
                    if _ue4ss_text:
                        try:
                            mod_ue4ss = json.loads(_ue4ss_text)
                        except Exception:
                            pass

            # Component detection from sub_contents directory structure
            _detected = []
            _has_lua = any(e["name"].lower() == "scripts" and e["type"] == "dir" for e in sub_contents)
            _has_cpp = any(e["name"].lower() == "dlls"    and e["type"] == "dir" for e in sub_contents)
            if _has_lua:
                _detected.append("lua")
            if _has_cpp:
                _detected.append("cpp")
            _bp_pak_files = []
            _lm_entry = next(
                (e for e in sub_contents if e["name"].lower() == "logicmods" and e["type"] == "dir"),
                None,
            )
            if _lm_entry:
                try:
                    _lm_contents = api.list_contents(_lm_entry["path"]) or []
                    _bp_pak_files = [
                        e["name"] for e in _lm_contents
                        if e.get("name", "").rsplit(".", 1)[-1].lower() in ("pak", "ucas", "utoc")
                    ]
                except Exception:
                    pass
                if _bp_pak_files:
                    _detected.append("blueprint")
            _bp_combined = bool(_bp_pak_files) and (_has_lua or _has_cpp)
            _components = _detected or ["lua"]  # AP mods default to lua if no dirs detected

            mods.append(DiscoveredMod(
                owner=owner,
                repo=repo,
                folder=folder_path,
                manifest=manifest,
                mod_id=mod_id,
                readme_url=readme_url,
                ue4ss_info=mod_ue4ss,
                templates_paths=templates_paths,
                components=_components,
                bp_pak_files=_bp_pak_files,
                bp_is_combined=_bp_combined,
                source_package_id=f"{owner}/{repo}",
            ))

        # Follow submodules recursively.
        # GitHub's directory listing returns submodule_git_url=null; fall back to
        # parsing .gitmodules to discover the remote URL.
        submodule_entries = [e for e in contents if e.get("type") == "submodule"]
        if submodule_entries:
            gitmodules_urls: dict[str, str] = {}
            gm_entry = next(
                (e for e in contents
                 if e.get("name") == ".gitmodules" and e.get("download_url")),
                None,
            )
            if gm_entry:
                gm_text = api.fetch_text(gm_entry["download_url"])
                if gm_text:
                    gitmodules_urls = _parse_gitmodules(gm_text)

        for entry in submodule_entries if submodule_entries else []:
            sub_url = (entry.get("submodule_git_url")
                       or gitmodules_urls.get(entry.get("path", ""), ""))
            if not sub_url:
                continue
            sub_mods = self.traverse(sub_url, cache, visited, depth + 1)
            parent_key = f"{owner}/{repo}"
            for _sm in sub_mods:
                if not _sm.submodule_of:
                    _sm.submodule_of = parent_key
                _sm.is_submodule_content = True
                if not _sm.source_package_id:
                    _sm.source_package_id = parent_key
            if not sub_mods:
                # Check if this submodule looks like a UE4SS repo and we have
                # a framework mod in the parent without ue4ss_info yet
                sub_parsed = parse_github_url(sub_url)
                if sub_parsed:
                    sub_repo_name = sub_parsed[1].lower()
                    if "ue4ss" in sub_repo_name:
                        synth_ue4ss = {
                            "options": [{
                                "type": "github_release",
                                "repo": f"{sub_parsed[0]}/{sub_parsed[1]}",
                                "tag": "latest",
                                "note": "From registry submodule",
                            }],
                            "docs": None,
                            "note": "",
                        }
                        # Attach to any core framework mod in this repo that lacks ue4ss_info
                        for mod in mods:
                            if _is_framework_mod_id(mod.mod_id) and not mod.ue4ss_info:
                                mod.ue4ss_info = synth_ue4ss
            mods.extend(sub_mods)

        # Synthetic container for template-only repos (no mods but has Templates/ dirs)
        if not mods and templates_paths:
            mods.append(DiscoveredMod(
                owner=owner,
                repo=repo,
                folder="",
                manifest={},
                mod_id="",
                readme_url="",
                ue4ss_info=None,
                templates_paths=templates_paths,
            ))

        # Cache successful result
        if mods:
            try:
                serialisable = [
                    {
                        "owner": m.owner,
                        "repo": m.repo,
                        "folder": m.folder,
                        "manifest": m.manifest,
                        "mod_id": m.mod_id,
                        "readme_url": m.readme_url,
                        "ue4ss_info": m.ue4ss_info,
                        "templates_paths": m.templates_paths,
                        "components": m.components,
                        "bp_pak_files": m.bp_pak_files,
                        "bp_is_combined": m.bp_is_combined,
                        "source_package_id": m.source_package_id,
                        "is_submodule_content": m.is_submodule_content,
                        "submodule_of": m.submodule_of,
                    }
                    for m in mods
                ]
                cache.set(cache_key, json.dumps(serialisable))
            except Exception:
                pass

        return mods

    # -----------------------------------------------------------------------
    # Folder tree — for the Repo Viewer (not cached, user-triggered only)
    # -----------------------------------------------------------------------

    def get_folder_tree(
        self,
        url: str,
        cache: "RegistryCache",
        game_id: str = "",
        existing_mod_ids: Optional[set] = None,
        visited: Optional[set] = None,
        depth: int = 0,
    ) -> Optional["FolderTreeNode"]:
        """
        Build a full hierarchical FolderTreeNode for the Repo Viewer.
        Not cached — only called on explicit user action (View button).
        Depth limit 3.
        """
        if depth > 3:
            return None
        if visited is None:
            visited = set()

        parsed = parse_github_url(url)
        if not parsed:
            return None
        owner, repo = parsed
        norm_key = f"{owner.lower()}/{repo.lower()}"
        if norm_key in visited:
            return None
        visited.add(norm_key)

        api = self._make_api(owner, repo)
        try:
            contents = api.list_contents("") or []
        except Exception:
            return None

        root = FolderTreeNode(
            node_type="root",
            name=repo,
            path="",
            owner=owner,
            repo=repo,
        )

        # Resolve submodule URLs from .gitmodules
        gitmodules_urls: dict[str, str] = {}
        gm_entry = next(
            (e for e in contents if e.get("name") == ".gitmodules" and e.get("download_url")),
            None,
        )
        if gm_entry:
            gm_text = api.fetch_text(gm_entry["download_url"])
            if gm_text:
                gitmodules_urls = _parse_gitmodules(gm_text)

        doc_nodes: list[FolderTreeNode] = []
        dir_nodes: list[FolderTreeNode] = []

        for entry in contents:
            ename = entry.get("name", "")
            etype = entry.get("type", "")
            epath = entry.get("path", ename)

            if etype == "file" and ename.lower().endswith(".md"):
                doc_nodes.append(FolderTreeNode(
                    node_type="file",
                    name=ename,
                    path=epath,
                    owner=owner,
                    repo=repo,
                    download_url=entry.get("download_url", ""),
                ))
            elif etype == "dir":
                node = self._build_dir_node(
                    owner, repo, entry, api, game_id, existing_mod_ids, depth
                )
                if node:
                    dir_nodes.append(node)
            elif etype == "submodule":
                sub_url = entry.get("submodule_git_url") or gitmodules_urls.get(epath, "")
                if sub_url:
                    sub_tree = self.get_folder_tree(
                        sub_url, cache, game_id, existing_mod_ids, visited, depth + 1
                    )
                    if sub_tree:
                        sub_tree.node_type = "submodule"
                        dir_nodes.append(sub_tree)

        # Sort: README.md first among docs, then other docs alphabetically; dirs alpha
        doc_nodes.sort(key=lambda n: (0 if n.name.lower() == "readme.md" else 1, n.name.lower()))
        dir_nodes.sort(key=lambda n: n.name.lower())

        root.children = doc_nodes + dir_nodes
        return root

    def _build_dir_node(
        self,
        owner: str,
        repo: str,
        entry: dict,
        api,
        game_id: str,
        existing_mod_ids: Optional[set],
        depth: int,
    ) -> Optional["FolderTreeNode"]:
        """Build a FolderTreeNode for one directory entry."""
        ename = entry.get("name", "")
        epath = entry.get("path", ename)

        try:
            sub_contents = api.list_contents(epath) or []
        except Exception:
            return FolderTreeNode(
                node_type="dir", name=ename, path=epath, owner=owner, repo=repo
            )

        # Determine node type
        node_type = "dir"
        mod: Optional[DiscoveredMod] = None
        game_id_match = True

        manifest_entry = next(
            (e for e in sub_contents if e.get("name") == "manifest.json"), None
        )
        if manifest_entry and manifest_entry.get("download_url"):
            manifest_text = api.fetch_text(manifest_entry["download_url"])
            if manifest_text:
                try:
                    manifest = json.loads(manifest_text)
                    _mod_id = manifest.get("mod_id", "")
                    if _mod_id:
                        node_type = "mod_dir"
                    else:
                        # manifest exists but no mod_id = treat as non-AP
                        node_type = "non_ap_mod"
                    readme_e = next(
                        (e for e in sub_contents
                         if e.get("name", "").lower() in ("readme.md", "readme.txt")),
                        None,
                    )
                    mod = DiscoveredMod(
                        owner=owner,
                        repo=repo,
                        folder=epath,
                        manifest=manifest,
                        mod_id=_mod_id,
                        readme_url=readme_e["download_url"] if readme_e and readme_e.get("download_url") else "",
                        source_package_id=f"{owner}/{repo}",
                    )
                    if _mod_id:
                        # Check game_id match
                        parts = _mod_id.split(".")
                        if game_id and len(parts) >= 2 and parts[1].lower() != game_id.lower():
                            game_id_match = False
                        # Check for ue4ss.json in same directory
                        ue4ss_e = next(
                            (e for e in sub_contents
                             if e.get("name") == "ue4ss.json" and e.get("download_url")),
                            None,
                        )
                        if ue4ss_e:
                            ue4ss_text = api.fetch_text(ue4ss_e["download_url"])
                            if ue4ss_text:
                                try:
                                    mod.ue4ss_info = json.loads(ue4ss_text)
                                except Exception:
                                    pass
                except Exception:
                    pass

        # Only direct children of Templates/ are template_dir (e.g. Templates/Palworld/).
        # Templates/ itself and deeper paths (e.g. Templates/Palworld/logic/) stay as dir.
        _eparts = epath.split("/")
        if len(_eparts) == 2 and _eparts[0] == "Templates":
            node_type = "template_dir"

        # Non-AP mod detection: if still "dir" (no manifest), check sub_contents for component dirs
        if node_type == "dir" and mod is None:
            _na_lua  = any(e.get("name","").lower() == "scripts"   and e.get("type") == "dir" for e in sub_contents)
            _na_cpp  = any(e.get("name","").lower() == "dlls"      and e.get("type") == "dir" for e in sub_contents)
            _na_lmd  = any(e.get("name","").lower() == "logicmods" and e.get("type") == "dir" for e in sub_contents)
            _na_paks = any(e.get("name","").lower().endswith(".pak")                            for e in sub_contents)
            _na_bp   = _na_lmd or _na_paks
            if _na_lua or _na_cpp or _na_bp:
                node_type = "non_ap_mod"
                _na_comps   = (["lua"] if _na_lua else []) + (["cpp"] if _na_cpp else []) + (["blueprint"] if _na_bp else [])
                _na_bp_paks = [e["name"] for e in sub_contents if e.get("name","").lower().endswith(".pak")]
                mod = DiscoveredMod(
                    owner=owner, repo=repo, folder=epath,
                    manifest={"name": ename}, mod_id="",
                    readme_url="", ue4ss_info=None, templates_paths=[],
                    components=_na_comps, bp_pak_files=_na_bp_paks,
                    bp_is_combined=_na_bp and (_na_lua or _na_cpp),
                    source_package_id=f"{owner}/{repo}",
                )

        # Component directory types — only if not already classified
        if node_type == "dir":
            _ename_lower = ename.lower()
            if _ename_lower == "scripts":
                node_type = "lua_dir"
            elif _ename_lower == "dlls":
                node_type = "cpp_dir"
            elif _ename_lower == "logicmods":
                node_type = "bp_dir"

        is_conflict = bool(
            mod and existing_mod_ids and mod.mod_id in existing_mod_ids
        )
        node = FolderTreeNode(
            node_type=node_type,
            name=ename,
            path=epath,
            owner=owner,
            repo=repo,
            mod=mod,
            game_id_match=game_id_match,
            conflict=is_conflict,
        )

        # Build children (docs first, then subdirs)
        doc_children: list[FolderTreeNode] = []
        dir_children: list[FolderTreeNode] = []
        is_template_node = (node_type == "template_dir")
        # Component directories show all files (not just .md) so users can see main.lua/main.dll
        is_component_dir = node_type in ("lua_dir", "cpp_dir", "bp_dir")

        for sub in sub_contents:
            sname = sub.get("name", "")
            stype = sub.get("type", "")
            spath = sub.get("path", f"{epath}/{sname}")

            if stype == "file" and (is_template_node or is_component_dir or sname.lower().endswith(".md")):
                doc_children.append(FolderTreeNode(
                    node_type="file",
                    name=sname,
                    path=spath,
                    owner=owner,
                    repo=repo,
                    download_url=sub.get("download_url", ""),
                ))
            elif stype == "dir" and depth < 3:
                child = self._build_dir_node(
                    owner, repo, sub, api, game_id, existing_mod_ids, depth + 1
                )
                if child:
                    dir_children.append(child)

        doc_children.sort(key=lambda n: (0 if n.name.lower() == "readme.md" else 1, n.name.lower()))
        dir_children.sort(key=lambda n: n.name.lower())
        node.children = doc_children + dir_children

        return node

    # -----------------------------------------------------------------------
    # Framework mod scoring
    # -----------------------------------------------------------------------

    def score_framework_candidates(
        self,
        candidates: list[DiscoveredMod],
        game_id: str,
        repo_meta: Optional[dict] = None,
    ) -> list[tuple[int, dict, DiscoveredMod]]:
        """
        Score framework mod candidates and return [(score, breakdown, mod)] descending.

        repo_meta: optional {"{owner}/{repo}": {"stars": int, "last_push_days": int}}
        for repos that have been pre-fetched via topic search.
        """
        results = []
        for mod in candidates:
            score = 0
            bd: dict = {}

            # mod_id exact match
            expected = f"archipelago.{game_id}.framework"
            if mod.mod_id == expected:
                score += 3
                bd["mod_id_match"] = 3

            # Naming convention (APFrameworkMod folder or repo name)
            folder_leaf = mod.folder.split("/")[-1] if mod.folder else ""
            if folder_leaf == "APFrameworkMod" or mod.repo == "APFrameworkMod":
                score += 2
                bd["naming_convention"] = 2

            # Repo freshness from pre-fetched meta
            meta = (repo_meta or {}).get(f"{mod.owner}/{mod.repo}", {})
            last_push_days = meta.get("last_push_days", 999)
            if last_push_days <= 90:
                score += 3
                bd["recent_push"] = 3

            # Stars (log10 curve, capped at 5)
            stars = meta.get("stars", 0)
            star_pts = min(5, int(math.log10(stars + 1) * 5))
            if star_pts:
                score += star_pts
                bd["stars"] = star_pts

            # UE4SS info presence
            if mod.ue4ss_info:
                score += 2
                bd["ue4ss_present"] = 2
            else:
                score -= 2
                bd["no_ue4ss"] = -2

            results.append((score, bd, mod))

        results.sort(key=lambda x: x[0], reverse=True)
        return results

    def score_mod_candidates(
        self,
        candidates: list[DiscoveredMod],
        game_id: str,
        repo_meta: Optional[dict] = None,
    ) -> list[tuple[int, dict, DiscoveredMod]]:
        """
        Score regular (non-framework) mod candidates and return
        [(score, breakdown, mod)] descending.

        Scoring table:
          mod_id valid format (archipelago.{game}.{name})  +2
          last push within 90 days                         +3
          stars: log10(stars+1) * 5, capped at 5           0–5
          has readme / documentation                        +1
          ue4ss.json found OR UE4SS submodule detected      +1
          dependencies declared in manifest                 +1

        repo_meta: optional {"{owner}/{repo}": {"stars": int, "last_push_days": int}}
        """
        results = []
        for mod in candidates:
            score = 0
            bd: dict = {}

            # Valid mod_id format: archipelago.{game}.{name}
            parts = mod.mod_id.split(".")
            if len(parts) >= 3 and parts[0] == "archipelago" and parts[1] == game_id:
                score += 2
                bd["valid_mod_id"] = 2

            # Repo freshness
            meta = (repo_meta or {}).get(f"{mod.owner}/{mod.repo}", {})
            last_push_days = meta.get("last_push_days", 999)
            if last_push_days <= 90:
                score += 3
                bd["recent_push"] = 3

            # Stars (log10 curve, capped at 5)
            stars = meta.get("stars", 0)
            star_pts = min(5, int(math.log10(stars + 1) * 5))
            if star_pts:
                score += star_pts
                bd["stars"] = star_pts

            # Has readme / documentation
            if mod.readme_url:
                score += 1
                bd["has_docs"] = 1

            # UE4SS info presence
            if mod.ue4ss_info:
                score += 1
                bd["ue4ss_present"] = 1

            # Dependencies declared in manifest
            if mod.manifest.get("depends"):
                score += 1
                bd["has_deps"] = 1

            results.append((score, bd, mod))

        results.sort(key=lambda x: x[0], reverse=True)
        return results

    # -----------------------------------------------------------------------
    # GitHub topic search
    # -----------------------------------------------------------------------

    def search_github(self, game_id: str, cache: "RegistryCache") -> list[dict]:
        """
        Search GitHub for repos tagged apf-ue4ss-registry-{game_id}.
        Cached for 1 hour.
        """
        from .registry_cache import TTL_SEARCH
        cache_key = f"search_{game_id}.json"
        cached = cache.get(cache_key, TTL_SEARCH)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

        results = self._call_search_api(f"apf-ue4ss-registry-{game_id}")
        if results:
            cache.set(cache_key, json.dumps(results))
        return results or []

    def search_github_core(self, game_id: str) -> list[dict]:
        """
        Search for repos tagged apf-ue4ss-registry-{game_id}-core.
        NOT cached — used for targeted UE4SS discovery.
        """
        topic = f"apf-ue4ss-registry-{game_id}-core"
        print(f"[P3-4][search_github_core] searching GitHub for topic={topic!r}")
        results = self._call_search_api(topic) or []
        _slugs = [r.get("owner", "?") + "/" + r.get("repo", "?") for r in results]
        print(f"[P3-4][search_github_core] GitHub search returned {len(results)} result(s): {_slugs}")
        return results

    def _call_search_api(self, topic: str) -> Optional[list[dict]]:
        api = self._make_api(_BLACKLIST_OWNER, _BLACKLIST_REPO)
        results = api.search_repos(f"topic:{topic}")
        return results if results is not None else None

    # -----------------------------------------------------------------------
    # Blacklist
    # -----------------------------------------------------------------------

    def fetch_blacklist(self) -> set[str]:
        """
        Fetch blacklist.json live from the APF repo.  Never cached to disk.
        In-memory TTL: 1 hour — ensures blacklist updates take effect within the session.
        """
        import time as _time
        import json as _json
        now = _time.time()
        if self._blacklist_cache is not None and now - self._blacklist_cache_time < 3600:
            return self._blacklist_cache

        raw_url = (
            f"https://raw.githubusercontent.com/{_BLACKLIST_OWNER}/"
            f"{_BLACKLIST_REPO}/master/tools/apf_manager/data/blacklist.json"
        )
        api = self._make_api(_BLACKLIST_OWNER, _BLACKLIST_REPO)
        text = api.fetch_text(raw_url, force_refresh=True)
        try:
            data = _json.loads(text) if text else {}
            self._blacklist_cache = {r.lower() for r in data.get("repos", [])}
            self._blacklist_cache_time = now
        except Exception:
            # On parse failure keep old cache and don't advance the timestamp
            if self._blacklist_cache is None:
                self._blacklist_cache = set()
        return self._blacklist_cache

    def is_blacklisted(self, owner: str, repo: str) -> bool:
        bl = self.fetch_blacklist()
        return f"{owner}/{repo}".lower() in bl

    def invalidate_blacklist_cache(self) -> None:
        """Force a fresh blacklist fetch on next check."""
        self._blacklist_cache = None
        self._blacklist_cache_time = 0.0

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _make_api(self, owner: str, repo: str):
        from ...core.remote.github_api import GitHubAPI
        token_path = _BUNDLED_PAT if _BUNDLED_PAT.exists() else None
        return GitHubAPI(
            repo_owner=owner,
            repo_name=repo,
            token_file_path=token_path,
            on_status=self._on_status,
        )

    def _load_bundled_token(self) -> Optional[str]:
        # 1. User PAT override
        user_override = Path.home() / ".apf_manager" / "github_token.json"
        if user_override.exists():
            try:
                data = json.loads(user_override.read_text(encoding="utf-8"))
                t = data.get("token", "").strip()
                if t:
                    return t
            except Exception:
                pass
        # 2. Bundled PAT
        if _BUNDLED_PAT.exists():
            try:
                t = _BUNDLED_PAT.read_text(encoding="utf-8").strip()
                if t:
                    return t
            except Exception:
                pass
        return None
