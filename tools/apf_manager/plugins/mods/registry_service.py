"""
RegistryService — manages user registries, mod discovery, staging, and install.

Service ID: "registry" — registered in plugins/mods/__init__.py.

All background operations (traversal, search) run on daemon threads and dispatch
results back to the main thread via Clock.schedule_once.
"""

from __future__ import annotations

import base64
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.plugin_host import PluginHost
    from .registry_resolver import DiscoveredMod
    from .registry_cache import RegistryCache


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RegistryEntry:
    url: str
    owner: str
    repo: str
    game_id: str = ""
    mod_count: int = 0
    last_refresh: Optional[datetime] = None
    status: str = "pending"    # "pending" | "ok" | "error" | "loading"
    error_msg: str = ""
    children: list["RegistryEntry"] = field(default_factory=list)
    selected_content: Optional[list] = None  # ["framework_mod:id", "mod:id", "ue4ss_option:...", "template:..."]


@dataclass
class RegistryModEntry:
    mod_id: str
    name: str
    owner: str
    repo: str
    folder: str
    description: str = ""
    readme_url: str = ""
    registry: Optional[RegistryEntry] = None
    ue4ss_info: Optional[dict] = None
    templates_paths: list = field(default_factory=list)
    components: list = field(default_factory=lambda: ["lua"])
    bp_pak_files: list = field(default_factory=list)
    bp_is_combined: bool = False
    source_package_id: str = ""   # "{owner}/{repo}" slug for grouping related content
    is_submodule_content: bool = False


@dataclass
class TemplateEntry:
    owner: str
    repo: str
    game_id: str
    path: str
    has_conflict: bool = False
    conflict_repos: list = field(default_factory=list)


@dataclass
class DocEntry:
    owner: str
    repo: str
    ref: str
    path: str
    raw_url: str
    title: str
    doc_type: str  # "mod" | "registry" | "ue4ss" | "template" | "general"


@dataclass
class FrameworkModCandidate:
    entry: RegistryModEntry
    score: int
    score_breakdown: dict
    in_chain: bool = True
    ue4ss_info: Optional[dict] = None


@dataclass
class UE4SSInfo:
    options: list
    docs: Optional[str] = None


@dataclass
class _OtherAsset:
    """A single downloadable asset within a GitHub release."""
    name: str               # filename (e.g. "UE4SS_v3.0.1.zip")
    url: str                # browser_download_url
    size: int = 0           # bytes; 0 = unknown
    selected: bool = False  # default: user must opt-in per asset


@dataclass
class _OtherEntry:
    """Represents a bootstrap content item from ue4ss.json options or a GitHub release."""
    name: str
    note: str
    type: str        # "github_release" | "external_url" | "manual"
    owner: str       # For github_release: UE4SS repo owner (may be a fork)
    repo: str        # For github_release: UE4SS repo name
    tag: str         # For github_release: exact release tag
    url: str         # For external_url / backwards-compat primary asset URL
    install_type: str = "ue4ss"   # "ue4ss" | "framework_binary"
    published_at: str = ""        # ISO date string from release
    asset_name: str = ""          # primary asset filename (backwards compat)
    changelog: str = ""           # first 2000 chars of release body
    assets: list = field(default_factory=list)  # list[_OtherAsset] — full asset list
    docs: str = ""               # relative path to documentation file in repo
    registry_owner: str = ""     # owner of registry repo that provided this option
    registry_repo:  str = ""     # repo of registry repo that provided this option
    prerelease: bool = False     # True if this is a pre-release/experimental
    content_hash: str = ""       # SHA-256 fingerprint for collision-proof expand keys
    has_duplicate_source: bool = False  # True when another entry targets the same endpoint


def _compute_other_entry_hash(entry: "_OtherEntry") -> str:
    """Compute a short SHA-256 content hash for stable expand/collapse key generation."""
    import hashlib
    fingerprint = "|".join([
        entry.owner or "",
        entry.repo or "",
        entry.tag or "",
        entry.install_type or "",
        entry.registry_owner or "",
        entry.registry_repo or "",
        entry.type or "",
    ])
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:20]


@dataclass
class RegistryError:
    error_type: str
    severity: str  # "error" | "warning"
    message: str
    affected: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# RegistryService
# ---------------------------------------------------------------------------

class RegistryService:
    """
    Manages user-added registries, traversal caching, mod staging, and install.

    Registered as the "registry" service by plugins/mods/__init__.py.
    """

    def __init__(self, host: "PluginHost") -> None:
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._lock = threading.Lock()

        # Lazy-initialised helpers
        self._cache: Optional["RegistryCache"] = None
        self._resolver = None

        # In-memory state (invalidated on game change)
        self._mods_cache: list[RegistryModEntry] = []
        self._mods_cache_game_id: str = ""
        self._staged: list[str] = []   # staged mod_ids

        # Rate limit dialog deduplication — None when no dialog is open
        self._rate_limit_dialog = None

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def on_game_changed(self, profile: Optional["GameProfile"]) -> None:
        with self._lock:
            self._profile = profile
            self._mods_cache = []
            self._mods_cache_game_id = ""
            self._staged = []

    # -----------------------------------------------------------------------
    # Registry management
    # -----------------------------------------------------------------------

    def get_user_registries(self, game_id: str = "") -> list[RegistryEntry]:
        """Return RegistryEntry objects for user-added registry URLs.

        If game_id is given, returns only registries associated with that game
        (plus any older entries that have no game_id stored).
        """
        from .registry_resolver import parse_github_url
        entries = []
        for r in self._host.config.get_user_registries(game_id):
            parsed = parse_github_url(r["url"])
            if not parsed:
                continue
            owner, repo = parsed
            entry = RegistryEntry(url=r["url"], owner=owner, repo=repo,
                                  game_id=r.get("game_id", ""),
                                  selected_content=r.get("selected_content"))
            added_at = r.get("added_at")
            if added_at:
                try:
                    entry.last_refresh = datetime.fromisoformat(added_at)
                except Exception:
                    pass
            entries.append(entry)
        return entries

    def add_registry(self, url: str, on_done: Callable[[bool, str], None]) -> None:
        """
        Validate and add a registry URL.
        Runs traversal on a background thread; calls on_done(success, msg) on main thread.
        """
        from .registry_resolver import parse_github_url
        parsed = parse_github_url(url)
        if not parsed:
            on_done(False, "Invalid GitHub URL — expected https://github.com/owner/repo")
            return

        owner, repo = parsed
        resolver = self._get_resolver()
        if resolver.is_blacklisted(owner, repo):
            on_done(False, "This repository is on the block list and cannot be added.")
            return

        def _bg():
            cache = self._get_cache()
            try:
                mods = resolver.traverse(url, cache)
            except Exception as exc:
                _ui(lambda: on_done(False, f"Traversal failed: {exc}"))
                return

            has_real_mods = any(m.mod_id for m in mods)
            has_templates = any(m.templates_paths for m in mods)
            if not has_real_mods and not has_templates:
                _ui(lambda: on_done(
                    False,
                    "No AP mods or templates found — is this a valid APF registry?"
                ))
                return

            # Derive game_id from mod_id (2nd component) or template path dir name.
            derived_game_id = ""
            for m in mods:
                if m.mod_id:
                    parts = m.mod_id.split(".")
                    if len(parts) >= 2:
                        derived_game_id = parts[1].lower()
                    break
            if not derived_game_id:
                for m in mods:
                    for tp in m.templates_paths:
                        game_dir = tp.split("/")[-1] if "/" in tp else tp
                        if game_dir:
                            derived_game_id = game_dir.lower()
                            break
                    if derived_game_id:
                        break

            # Reject if the registry targets a different game than the current profile.
            current_game_id = self._get_game_id() or ""
            if current_game_id and derived_game_id and derived_game_id != current_game_id:
                _ui(lambda: on_done(
                    False,
                    f"No content found for '{current_game_id}' — this registry targets a different game."
                ))
                return

            # Count selectable content items to decide whether to show the viewer.
            mod_items = [m for m in mods if m.mod_id]
            tpl_items = [tp for m in mods for tp in m.templates_paths]
            content_count = len(mod_items) + len(tpl_items)

            # Compute existing mod_ids for conflict detection in the viewer.
            existing_mod_ids: set = set()
            for reg_entry in self.get_user_registries():
                try:
                    reg_mods = resolver.traverse(reg_entry.url, cache)
                    existing_mod_ids.update(m.mod_id for m in reg_mods if m.mod_id)
                except Exception:
                    pass

            def _finalize(selected_mods, raw_selected_ids=None):
                """Called by Repo Viewer on_confirm (main thread) or directly."""
                from .registry_resolver import _is_framework_mod_id
                ap_count     = sum(1 for m in selected_mods if m.mod_id)
                non_ap_count = sum(1 for m in selected_mods if not m.mod_id)
                parts = [f"{ap_count} AP mod(s)"] if ap_count else []
                if non_ap_count:
                    parts.append(f"{non_ap_count} non-AP mod(s)")
                summary = ", ".join(parts) if parts else "no mods"
                # Build selected_content from checked mods + raw SPA item IDs
                sc: Optional[list] = None
                if raw_selected_ids is not None:
                    sc = []
                    for m in selected_mods:
                        key = m.mod_id or m.folder
                        if key:
                            prefix = "framework_mod" if _is_framework_mod_id(m.mod_id) else "mod"
                            sc.append(f"{prefix}:{key}")
                    for sid in raw_selected_ids:
                        if sid.startswith("ue4ss:"):
                            sc.append(f"ue4ss_option:{sid[len('ue4ss:'):]}")
                        elif sid.startswith("tpl:"):
                            parts_tpl = sid[len("tpl:"):].split(":", 1)
                            if len(parts_tpl) == 2:
                                sc.append(f"template:{parts_tpl[1]}")
                self._host.config.add_user_registry(url, game_id=derived_game_id,
                                                     selected_content=sc)
                self._invalidate_mods_cache()
                _ui(lambda: on_done(True, f"Registry added — {summary} found."))

            if content_count > 1 and self._host.has_service("repo_viewer"):
                game_id_for_viewer = current_game_id or derived_game_id
                _eids = existing_mod_ids
                _ui(lambda: self._host.show_dialog(
                    "repo_viewer",
                    repo_url=url,
                    game_id=game_id_for_viewer,
                    traversal_result=mods,
                    existing_mod_ids=_eids,
                    on_confirm=_finalize,
                    on_cancel=lambda: _ui(lambda: on_done(False, "Cancelled.")),
                ))
            else:
                _finalize(mods)

        threading.Thread(target=_bg, daemon=True).start()

    def add_registry_with_viewer(
        self,
        url: str,
        game_id: str,
        on_done: Callable[[bool, str], None],
    ) -> None:
        """
        Like add_registry(), but always opens the Repo Viewer (unless blacklisted).
        Passes the full folder tree to the viewer so the sidebar shows real structure.
        """
        from .registry_resolver import parse_github_url, FolderTreeNode
        parsed = parse_github_url(url)
        if not parsed:
            on_done(False, "Invalid GitHub URL — expected https://github.com/owner/repo")
            return

        owner, repo = parsed
        resolver = self._get_resolver()
        if resolver.is_blacklisted(owner, repo):
            on_done(False, "This repository is on the block list and cannot be added.")
            return

        def _bg():
            cache = self._get_cache()
            try:
                mods = resolver.traverse(url, cache)
            except Exception as exc:
                _ui(lambda: on_done(False, f"Traversal failed: {exc}"))
                return

            # For the viewer we accept any repo (empty repos show empty tree)
            # Derive game_id to save with config
            derived_game_id = game_id or ""
            if not derived_game_id:
                for m in mods:
                    if m.mod_id:
                        parts = m.mod_id.split(".")
                        if len(parts) >= 2:
                            derived_game_id = parts[1].lower()
                        break
            if not derived_game_id:
                for m in mods:
                    for tp in m.templates_paths:
                        gdir = tp.split("/")[-1] if "/" in tp else tp
                        if gdir:
                            derived_game_id = gdir.lower()
                            break
                    if derived_game_id:
                        break

            # Reject if no valid content found for the current game
            current_game_id = (self._get_game_id() or "").lower()
            if current_game_id:
                valid_count = 0
                for m in mods:
                    if m.mod_id:
                        _parts = m.mod_id.split(".")
                        if len(_parts) >= 2 and _parts[1].lower() == current_game_id:
                            valid_count += 1
                    for tp in m.templates_paths:
                        _gdir = (tp.split("/")[-1] if "/" in tp else tp).lower()
                        if _gdir == current_game_id:
                            valid_count += 1
                if valid_count == 0:
                    _ui(lambda: on_done(
                        False,
                        f"This registry has no content for '{current_game_id}'. "
                        f"It may be intended for a different game."
                    ))
                    return

            # Existing mod_ids for conflict detection
            existing_mod_ids: set = set()
            for reg_entry in self.get_user_registries():
                try:
                    reg_mods = resolver.traverse(reg_entry.url, cache)
                    existing_mod_ids.update(m.mod_id for m in reg_mods if m.mod_id)
                except Exception:
                    pass

            # Build folder tree
            try:
                folder_tree = resolver.get_folder_tree(
                    url, cache, game_id=derived_game_id or game_id,
                    existing_mod_ids=existing_mod_ids,
                )
            except Exception:
                folder_tree = None

            def _finalize(selected_mods, raw_selected_ids=None):
                from .registry_resolver import _is_framework_mod_id
                ap_count     = sum(1 for m in selected_mods if m.mod_id)
                non_ap_count = sum(1 for m in selected_mods if not m.mod_id)
                parts = [f"{ap_count} AP mod(s)"] if ap_count else []
                if non_ap_count:
                    parts.append(f"{non_ap_count} non-AP mod(s)")
                summary = ", ".join(parts) if parts else "no mods"
                sc: Optional[list] = None
                if raw_selected_ids is not None:
                    sc = []
                    for m in selected_mods:
                        key = m.mod_id or m.folder
                        if key:
                            prefix = "framework_mod" if _is_framework_mod_id(m.mod_id) else "mod"
                            sc.append(f"{prefix}:{key}")
                    for sid in raw_selected_ids:
                        if sid.startswith("ue4ss:"):
                            sc.append(f"ue4ss_option:{sid[len('ue4ss:'):]}")
                        elif sid.startswith("tpl:"):
                            parts_tpl = sid[len("tpl:"):].split(":", 1)
                            if len(parts_tpl) == 2:
                                sc.append(f"template:{parts_tpl[1]}")
                self._host.config.add_user_registry(url, game_id=derived_game_id,
                                                     selected_content=sc)
                self._invalidate_mods_cache()
                _ui(lambda: on_done(True, f"Registry added — {summary} found."))

            if not self._host.has_service("repo_viewer"):
                # Fallback: add directly without viewer
                _finalize(mods)
                return

            _ft = folder_tree
            _eids = existing_mod_ids
            _ui(lambda: self._host.show_dialog(
                "repo_viewer",
                repo_url=url,
                game_id=derived_game_id or game_id,
                traversal_result=mods,
                folder_tree=_ft,
                existing_mod_ids=_eids,
                on_confirm=_finalize,
                on_cancel=lambda: _ui(lambda: on_done(False, "Cancelled.")),
            ))

        threading.Thread(target=_bg, daemon=True).start()

    def remove_registry(self, url: str) -> None:
        """Remove a user registry URL and invalidate the mods cache."""
        self._host.config.remove_user_registry(url)
        self._invalidate_mods_cache()

    def refresh_all(self, on_done: Optional[Callable] = None) -> None:
        """Re-traverse all registered repos (bypass traversal cache), then call on_done."""
        def _bg():
            cache = self._get_cache()
            resolver = self._get_resolver()
            for entry in self.get_user_registries():
                cache_key = f"{entry.owner}+{entry.repo}/traversal.json"
                cache.invalidate(cache_key)
                try:
                    resolver.traverse(entry.url, cache)
                except Exception as exc:
                    self._host.log(f"[registry] Refresh failed for {entry.url}: {exc}")
            self._invalidate_mods_cache()
            if on_done:
                _ui(on_done)

        threading.Thread(target=_bg, daemon=True).start()

    def search_github(self, game_id: str, on_done: Callable[[list[dict]], None]) -> None:
        """
        Search GitHub for repos tagged apf-ue4ss-registry-{game_id}.
        Results are cached; calls on_done(results) on main thread.
        """
        def _bg():
            resolver = self._get_resolver()
            cache = self._get_cache()
            results = resolver.search_github(game_id, cache)
            _ui(lambda: on_done(results))

        threading.Thread(target=_bg, daemon=True).start()

    def is_blacklisted(self, owner: str, repo: str) -> bool:
        return self._get_resolver().is_blacklisted(owner, repo)

    # -----------------------------------------------------------------------
    # Mod / template discovery
    # -----------------------------------------------------------------------

    def get_mods(self, game_id: str) -> list[RegistryModEntry]:
        """Return all mods from all registered registries, filtered by game_id."""
        with self._lock:
            if self._mods_cache and self._mods_cache_game_id == game_id:
                return list(self._mods_cache)

        mods = self._load_mods(game_id)

        with self._lock:
            self._mods_cache = mods
            self._mods_cache_game_id = game_id
        return mods

    def _load_mods(self, game_id: str) -> list[RegistryModEntry]:
        resolver = self._get_resolver()
        cache = self._get_cache()
        results: list[RegistryModEntry] = []

        for entry in self.get_user_registries():
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception as exc:
                self._host.log(f"[registry] Traversal error for {entry.url}: {exc}")
                continue

            # Build selected key set from stored selection (None = include all)
            selected_content = set(entry.selected_content or [])
            selected_mod_keys = (
                {s[len("mod:"):] for s in selected_content if s.startswith("mod:")} |
                {s[len("framework_mod:"):] for s in selected_content if s.startswith("framework_mod:")}
            ) if selected_content else None

            for mod in discovered:
                # Skip synthetic container entries with no mod content
                if not mod.mod_id and not mod.components:
                    continue
                # AP mods: filter by game_id (2nd component of mod_id, e.g. "palworld")
                if mod.mod_id:
                    parts = mod.mod_id.split(".")
                    if game_id and len(parts) >= 2 and parts[1].lower() != game_id.lower():
                        continue
                    if selected_mod_keys is not None and mod.mod_id not in selected_mod_keys:
                        continue
                # Non-AP mods: filter by the registry's stored game_id
                else:
                    if game_id and entry.game_id and entry.game_id.lower() != game_id.lower():
                        continue
                    if selected_mod_keys is not None and mod.folder not in selected_mod_keys:
                        continue
                results.append(RegistryModEntry(
                    mod_id=mod.mod_id,
                    name=mod.manifest.get("name") or mod.folder.split("/")[-1],
                    owner=mod.owner,
                    repo=mod.repo,
                    folder=mod.folder,
                    description=mod.manifest.get("description", ""),
                    readme_url=mod.readme_url,
                    registry=entry,
                    ue4ss_info=mod.ue4ss_info,
                    templates_paths=mod.templates_paths,
                    components=mod.components,
                    bp_pak_files=mod.bp_pak_files,
                    bp_is_combined=getattr(mod, "bp_is_combined", False),
                    source_package_id=getattr(mod, "source_package_id", f"{mod.owner}/{mod.repo}"),
                    is_submodule_content=getattr(mod, "is_submodule_content", False),
                ))

        return results

    def get_templates(self, game_id: str) -> list[TemplateEntry]:
        """Return template entries aggregated across all registries for game_id."""
        resolver = self._get_resolver()
        cache = self._get_cache()
        # path → ["{owner}/{repo}", ...]
        seen: dict[str, list[str]] = {}

        for entry in self.get_user_registries():
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception:
                continue
            selected_content = set(entry.selected_content or [])
            for mod in discovered:
                for tpath in mod.templates_paths:
                    # tpath is like "Templates/Palworld"
                    game_dir = tpath.split("/")[-1] if "/" in tpath else tpath
                    if game_id and game_dir.lower() != game_id.lower():
                        continue
                    if selected_content and f"template:{tpath}" not in selected_content:
                        continue
                    repo_key = f"{mod.owner}/{mod.repo}"
                    existing = seen.setdefault(tpath, [])
                    if repo_key not in existing:
                        existing.append(repo_key)

        results: list[TemplateEntry] = []
        for tpath, repos in seen.items():
            game_dir = tpath.split("/")[-1] if "/" in tpath else tpath
            first_owner, first_repo = repos[0].split("/", 1)
            results.append(TemplateEntry(
                owner=first_owner,
                repo=first_repo,
                game_id=game_dir,
                path=tpath,
                has_conflict=len(repos) > 1,
                conflict_repos=repos,
            ))
        return results

    def get_other_content(self, game_id: str) -> list:
        """Return _OtherEntry list for UE4SS options from ue4ss.json in game registries."""
        from .registry_resolver import _is_framework_mod_id
        for entry in self.get_mods(game_id):
            if entry.ue4ss_info and _is_framework_mod_id(entry.mod_id):
                info = entry.ue4ss_info
                reg = entry.registry
                reg_owner = reg.owner if reg else ""
                reg_repo  = reg.repo  if reg else ""
                selected_content = set(reg.selected_content or []) if reg else set()
                entries = []
                for opt in info.get("options", []):
                    opt_type = opt.get("type", "manual")
                    raw_repo = opt.get("repo", "")
                    owner, repo = raw_repo.split("/", 1) if "/" in raw_repo else ("", raw_repo)
                    tag = opt.get("tag", "")
                    # Filter by per-option selection if a selection was made in repo viewer
                    if selected_content:
                        opt_key = f"ue4ss_option:{raw_repo}:{tag}"
                        if opt_key not in selected_content:
                            continue
                    entries.append(_OtherEntry(
                        name           = opt.get("note", "UE4SS"),
                        note           = opt.get("note", ""),
                        type           = opt_type,
                        owner          = owner,
                        repo           = repo,
                        tag            = tag,
                        url            = opt.get("url", ""),
                        install_type   = "ue4ss",
                        docs           = opt.get("docs", ""),
                        registry_owner = reg_owner,
                        registry_repo  = reg_repo,
                    ))
                return entries
        return []

    def get_framework_candidates(self, game_id: str) -> list[FrameworkModCandidate]:
        """Return scored framework mod candidates from all registered registries."""
        mods = self.get_mods(game_id)
        from .registry_resolver import _is_framework_mod_id
        fw_mods = [m for m in mods if _is_framework_mod_id(m.mod_id)]
        if not fw_mods:
            return []

        resolver = self._get_resolver()
        scored = resolver.score_framework_candidates(
            [_to_discovered(m) for m in fw_mods],
            game_id,
        )
        id_to_entry = {m.mod_id: m for m in fw_mods}
        return [
            FrameworkModCandidate(
                entry=id_to_entry[disc.mod_id],
                score=score,
                score_breakdown=bd,
                in_chain=True,
                ue4ss_info=disc.ue4ss_info,
            )
            for score, bd, disc in scored
            if disc.mod_id in id_to_entry
        ]

    def get_ue4ss_info(self, game_id: str) -> Optional[UE4SSInfo]:
        """
        Discover UE4SS installation options from user-registered registry data only.

        Returns None when no game-specific UE4SS info is found.
        Callers that need a bootstrap path should use UpdatesService.get_ue4ss_releases_for_content().
        """
        from .registry_resolver import _is_framework_mod_id
        for entry in self.get_mods(game_id):
            if entry.ue4ss_info and _is_framework_mod_id(entry.mod_id):
                info = entry.ue4ss_info
                return UE4SSInfo(
                    options=info.get("options", []),
                    docs=info.get("docs"),
                )
        return None

    # -----------------------------------------------------------------------
    # Staged queue
    # -----------------------------------------------------------------------

    def stage_mod(self, mod_id: str) -> None:
        with self._lock:
            if mod_id not in self._staged:
                self._staged.append(mod_id)

    def unstage_mod(self, mod_id: str) -> None:
        with self._lock:
            self._staged = [s for s in self._staged if s != mod_id]

    def get_staged(self) -> list[RegistryModEntry]:
        game_id = self._get_game_id() or ""
        all_mods = self.get_mods(game_id)
        id_to_mod = {m.mod_id: m for m in all_mods}
        with self._lock:
            return [id_to_mod[sid] for sid in self._staged if sid in id_to_mod]

    def validate_queue(self, game_id: str) -> list[RegistryError]:
        errors: list[RegistryError] = []
        staged = self.get_staged()
        candidates = self.get_framework_candidates(game_id)

        if not candidates:
            errors.append(RegistryError(
                error_type="no_framework_mod",
                severity="error",
                message="No framework mod candidate found — install is blocked.",
            ))

        # Duplicate mod_ids in staged queue
        seen: dict[str, int] = {}
        for m in staged:
            seen[m.mod_id] = seen.get(m.mod_id, 0) + 1
        for mid, count in seen.items():
            if count > 1:
                errors.append(RegistryError(
                    error_type="duplicate_mod_id",
                    severity="error",
                    message=f"Duplicate mod staged: {mid} ({count}×).",
                    affected=[mid],
                ))

        return errors

    def install_queue(
        self,
        game_id: str,
        on_progress: Callable[[str], None],
        on_done: Callable[[bool, str], None],
    ) -> None:
        """Install all staged mods. Blocking work runs on a background thread."""
        errors = self.validate_queue(game_id)
        blocking = [e for e in errors if e.severity == "error"]
        if blocking:
            on_done(False, blocking[0].message)
            return

        def _bg():
            staged = self.get_staged()
            for mod in staged:
                _ui(lambda m=mod: on_progress(f"Installing {m.name}…"))
                # TODO: download mod files and run install steps
            _ui(lambda: on_done(True, f"Installed {len(staged)} mod(s)."))

        threading.Thread(target=_bg, daemon=True).start()

    # -----------------------------------------------------------------------
    # Docs
    # -----------------------------------------------------------------------

    def get_mod_docs(self, entry: RegistryModEntry) -> list[DocEntry]:
        docs = []
        if entry.readme_url:
            docs.append(DocEntry(
                owner=entry.owner,
                repo=entry.repo,
                ref="HEAD",
                path=f"{entry.folder}/README.md",
                raw_url=entry.readme_url,
                title=f"{entry.name} — README",
                doc_type="mod",
            ))
        return docs

    def get_registry_docs(self, entry: RegistryEntry) -> list[DocEntry]:
        api = self._make_api(entry.owner, entry.repo)
        try:
            contents = api.list_contents("")
        except Exception:
            return []
        docs = []
        root_readme = next(
            (e for e in contents if e["name"].lower() == "readme.md"), None
        )
        if root_readme and root_readme.get("download_url"):
            docs.append(DocEntry(
                owner=entry.owner,
                repo=entry.repo,
                ref="HEAD",
                path="README.md",
                raw_url=root_readme["download_url"],
                title=f"{entry.repo} — README",
                doc_type="registry",
            ))
        docs_dir = next(
            (e for e in contents if e["name"] == "docs" and e["type"] == "dir"), None
        )
        if docs_dir:
            try:
                sub = api.list_contents("docs")
                for f in sub:
                    if f["name"].endswith(".md") and f.get("download_url"):
                        docs.append(DocEntry(
                            owner=entry.owner,
                            repo=entry.repo,
                            ref="HEAD",
                            path=f["path"],
                            raw_url=f["download_url"],
                            title=f["name"].replace(".md", "").replace("_", " ").title(),
                            doc_type="registry",
                        ))
            except Exception:
                pass
        return docs

    # -----------------------------------------------------------------------
    # Share / import
    # -----------------------------------------------------------------------

    def export_registries_b64(self) -> str:
        urls = [r["url"] for r in self._host.config.get_user_registries()]
        payload = {"apf_registry_share": "v1", "registries": urls}
        return base64.b64encode(json.dumps(payload).encode()).decode()

    def import_registries_b64(self, encoded: str) -> list[str]:
        """Decode a share payload and return the list of registry URLs."""
        try:
            data = json.loads(base64.b64decode(encoded.strip().encode()).decode())
            if data.get("apf_registry_share") != "v1":
                return []
            return data.get("registries", [])
        except Exception:
            return []

    @staticmethod
    def is_share_payload(text: str) -> bool:
        """Return True if text looks like a base64 registry share payload."""
        try:
            data = json.loads(base64.b64decode(text.strip().encode()).decode())
            return data.get("apf_registry_share") == "v1"
        except Exception:
            return False

    # -----------------------------------------------------------------------
    # Capabilities (for DevTools CI)
    # -----------------------------------------------------------------------

    def build_capabilities(self, game_id: str) -> dict:
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            return mods_svc.build_capabilities()
        return {}

    def get_templates_dirs(self, game_id: str) -> list[Path]:
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            return mods_svc._resolve_templates_dirs()
        return []

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _get_cache(self) -> "RegistryCache":
        if self._cache is None:
            from .registry_cache import RegistryCache
            self._cache = RegistryCache()
        return self._cache

    def _get_resolver(self):
        if self._resolver is None:
            from .registry_resolver import RegistryResolver
            self._resolver = RegistryResolver(on_status=self._on_status)
        return self._resolver

    def _on_status(self, level: str, msg: str) -> None:
        if level == "rate_limit_exceeded":
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt, m=msg: self._show_rate_limit_dialog(m))
            return
        if level == "rate_limit_exceeded_search":
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt, m=msg: self._show_search_rate_limit_dialog(m))
            return
        if level == "debug":
            self._host.log(f"[registry] {msg}")
            return
        self._host.log(f"[registry] [{level.upper()}] {msg}")

    def _show_rate_limit_dialog(self, reset_str: str) -> None:
        if self._rate_limit_dialog is not None:
            return  # dialog already open — don't stack duplicates
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        from kivymd.uix.button import MDButton, MDButtonText
        def _close(*_):
            if self._rate_limit_dialog:
                self._rate_limit_dialog.dismiss()
            self._rate_limit_dialog = None
        self._rate_limit_dialog = MDDialog(
            MDDialogHeadlineText(text="GitHub Rate Limit Reached"),
            MDDialogSupportingText(
                text=(
                    "Too many requests have been made to the GitHub API. "
                    "Registry browsing is unavailable until the limit resets.\n\n"
                    f"Expected to reset at: {reset_str}"
                )
            ),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="OK"), style="text", on_release=_close),
            ),
        )
        self._rate_limit_dialog.open()

    def _show_search_rate_limit_dialog(self, reset_str: str) -> None:
        if self._rate_limit_dialog is not None:
            return  # dialog already open — don't stack duplicates
        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )
        from kivymd.uix.button import MDButton, MDButtonText
        def _close(*_):
            if self._rate_limit_dialog:
                self._rate_limit_dialog.dismiss()
            self._rate_limit_dialog = None
        self._rate_limit_dialog = MDDialog(
            MDDialogHeadlineText(text="GitHub Search Limit Reached"),
            MDDialogSupportingText(
                text=(
                    "The GitHub search API allows 30 requests per minute. "
                    "Registry search is temporarily unavailable.\n\n"
                    f"Expected to reset at: {reset_str}"
                )
            ),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="OK"), style="text", on_release=_close),
            ),
        )
        self._rate_limit_dialog.open()

    def _invalidate_mods_cache(self) -> None:
        with self._lock:
            self._mods_cache = []
            self._mods_cache_game_id = ""

    def _get_game_id(self) -> Optional[str]:
        """
        Derive the game_id string (e.g. 'palworld') for registry filtering.

        Priority:
          1. Installed framework mod's mod_id (e.g. 'archipelago.palworld.framework' → 'palworld')
          2. Game profile display name, normalised
        """
        from .registry_resolver import _is_framework_mod_id
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            for mod in mods_svc.get_ap_mods():
                if mod.mod_id and _is_framework_mod_id(mod.mod_id):
                    parts = mod.mod_id.split(".")
                    if len(parts) >= 2:
                        return parts[1]
        if self._profile:
            return self._profile.display_name.lower().replace(" ", "_")
        return None

    def _make_api(self, owner: str, repo: str):
        from ...core.remote.github_api import GitHubAPI
        from .registry_resolver import _BUNDLED_PAT
        token_path = _BUNDLED_PAT if _BUNDLED_PAT.exists() else None
        return GitHubAPI(
            repo_owner=owner,
            repo_name=repo,
            token_file_path=token_path,
            on_status=self._on_status,
        )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _to_discovered(entry: RegistryModEntry) -> "DiscoveredMod":
    """Convert a RegistryModEntry back to a DiscoveredMod for scoring."""
    from .registry_resolver import DiscoveredMod
    return DiscoveredMod(
        owner=entry.owner,
        repo=entry.repo,
        folder=entry.folder,
        manifest={
            "mod_id": entry.mod_id,
            "name": entry.name,
            "description": entry.description,
        },
        mod_id=entry.mod_id,
        readme_url=entry.readme_url,
        ue4ss_info=entry.ue4ss_info,
        templates_paths=entry.templates_paths,
        components=entry.components,
        bp_pak_files=entry.bp_pak_files,
    )


def _ui(fn: Callable) -> None:
    """Schedule fn on the Kivy main thread."""
    from kivy.clock import Clock
    Clock.schedule_once(lambda dt: fn(), 0)
