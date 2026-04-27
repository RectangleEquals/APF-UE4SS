"""
RegistryService — manages user registries, mod discovery, staging, and install.

Service ID: "registry" — registered in plugins/mods/__init__.py.

All background operations (traversal, search) run on daemon threads and dispatch
results back to the main thread via Clock.schedule_once.
"""

from __future__ import annotations

import base64
import json
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Callable, TYPE_CHECKING

from ..shared.data.content_base import GitHubRepo, RegistrySource, ModComponents, DocInfo, ContentTags
from ..shared.data.content_types import (
    RegistryDescriptor, APModDescriptor, FrameworkModDescriptor, ThirdPartyModDescriptor,
    TemplateDescriptor, GithubReleaseBinary, ExternalUrlBinary, ManualBinary, ReleaseSource,
    BinaryDescriptor,
)
from ..shared.data.content_filter import ContentFilter
from ..utils.registry.viewer import RegistryViewer

if TYPE_CHECKING:
    from ....core.config import GameProfile
    from ....core.plugin_host import PluginHost
    from ..utils.registry.resolver import DiscoveredMod
    from ..utils.registry.cache import RegistryCache


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
    entry: object
    score: int
    score_breakdown: dict
    in_chain: bool = True
    ue4ss_info: Optional[dict] = None


@dataclass
class UE4SSInfo:
    options: list
    docs: Optional[str] = None


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
        self._mods_cache: list = []
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

    def get_user_registries(self, game_id: str = "") -> list[RegistryDescriptor]:
        """Return RegistryDescriptor objects for user-added registry URLs."""
        from ..utils.registry.resolver import parse_github_url
        entries = []
        for r in self._host.config.get_user_registries(game_id):
            parsed = parse_github_url(r["url"])
            if not parsed:
                continue
            owner, repo_name = parsed
            entry = RegistryDescriptor(
                url=r["url"],
                repo=GitHubRepo(owner=owner, repo=repo_name),
                game_id=r.get("game_id", ""),
                selected_content=r.get("selected_content"),
            )
            added_at = r.get("added_at")
            if added_at:
                entry.last_refresh = added_at
            entries.append(entry)
        return entries

    def add_registry(self, url: str, on_done: Callable[[bool, str], None]) -> None:
        """
        Validate and add a registry URL.
        Runs traversal on a background thread; calls on_done(success, msg) on main thread.
        """
        from ..utils.registry.resolver import parse_github_url
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

            # DUP = already in Content tab from a different source.
            # Use get_mods() which reflects actual selected_content state.
            current_game_id = self._get_game_id() or ""
            existing_mod_ids: set = {
                getattr(m, "mod_id", "") for m in self.get_mods(current_game_id)
                if getattr(m, "mod_id", "")
            }

            def _finalize(selected_mods, raw_selected_ids=None):
                ap_count     = sum(1 for m in selected_mods if m.mod_id)
                non_ap_count = sum(1 for m in selected_mods if not m.mod_id)
                parts = [f"{ap_count} AP mod(s)"] if ap_count else []
                if non_ap_count:
                    parts.append(f"{non_ap_count} non-AP mod(s)")
                summary = ", ".join(parts) if parts else "no mods"
                sc = _build_sc_from_viewer_result(selected_mods, raw_selected_ids)
                self._host.config.add_user_registry(url, game_id=derived_game_id,
                                                     selected_content=sc)
                self._invalidate_mods_cache()
                _ui(lambda: on_done(True, f"Registry added — {summary} found."))

            if content_count > 1:
                game_id_for_viewer = current_game_id or derived_game_id
                _eids = existing_mod_ids
                _esc = self._get_existing_sc(url)
                _ui(lambda: RegistryViewer(self._host).show(
                    repo_url=url,
                    game_id=game_id_for_viewer,
                    traversal_result=mods,
                    existing_mod_ids=_eids,
                    initial_selected_content=_esc,
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
        from ..utils.registry.resolver import parse_github_url, FolderTreeNode
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

            # DUP = already in Content tab from a different source.
            # Use get_mods() which reflects actual selected_content state.
            existing_mod_ids: set = {
                getattr(m, "mod_id", "") for m in self.get_mods(current_game_id)
                if getattr(m, "mod_id", "")
            }

            # Build folder tree
            try:
                folder_tree = resolver.get_folder_tree(
                    url, cache, game_id=derived_game_id or game_id,
                    existing_mod_ids=existing_mod_ids,
                )
            except Exception:
                folder_tree = None

            def _finalize(selected_mods, raw_selected_ids=None):
                ap_count     = sum(1 for m in selected_mods if m.mod_id)
                non_ap_count = sum(1 for m in selected_mods if not m.mod_id)
                parts = [f"{ap_count} AP mod(s)"] if ap_count else []
                if non_ap_count:
                    parts.append(f"{non_ap_count} non-AP mod(s)")
                summary = ", ".join(parts) if parts else "no mods"
                sc = _build_sc_from_viewer_result(selected_mods, raw_selected_ids)
                self._host.config.add_user_registry(url, game_id=derived_game_id,
                                                     selected_content=sc)
                self._invalidate_mods_cache()
                _ui(lambda: on_done(True, f"Registry added — {summary} found."))

            _ft = folder_tree
            _eids = existing_mod_ids
            _esc = self._get_existing_sc(url)
            _ui(lambda: RegistryViewer(self._host).show(
                repo_url=url,
                game_id=derived_game_id or game_id,
                traversal_result=mods,
                folder_tree=_ft,
                existing_mod_ids=_eids,
                initial_selected_content=_esc,
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
                cache_key = f"{entry.repo.owner}+{entry.repo.repo}/traversal.json"
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

    def get_mods(self, game_id: str) -> list:
        """Return all mods from all registered registries, filtered by game_id."""
        with self._lock:
            if self._mods_cache and self._mods_cache_game_id == game_id:
                return list(self._mods_cache)

        mods = self._load_mods(game_id)

        with self._lock:
            self._mods_cache = mods
            self._mods_cache_game_id = game_id

        # K-3 Fix C: pre-warm the docs cache so the viewer is fast on first open.
        # Runs on a daemon thread — never blocks the caller.
        threading.Thread(
            target=self._prefetch_docs_bg,
            args=(list(mods),),
            daemon=True,
        ).start()

        return mods

    def _prefetch_docs_bg(self, mods: list) -> None:
        """Background pre-fetch for all mod README files.

        GitHubAPI.fetch_text caches responses with a 24-hour TTL, so this is a
        no-op when the cache is warm. On a cold start, it warms the cache so the
        in-app docs viewer opens instantly without a network round-trip.
        """
        try:
            for mod in mods:
                _docs = getattr(mod, "docs", None)
                if not _docs:
                    continue
                url = getattr(_docs, "readme_url", "")
                if not url or not url.startswith("http"):
                    continue
                _src = getattr(mod, "source", None)
                if not _src:
                    continue
                try:
                    api = self._make_api(_src.repo.owner, _src.repo.repo)
                    api.fetch_text(url, force_refresh=False)
                except Exception:
                    pass
        except Exception:
            pass

    def _load_mods(self, game_id: str) -> list:
        resolver = self._get_resolver()
        cache = self._get_cache()
        results = []

        for entry in self.get_user_registries():
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception as exc:
                self._host.log(f"[registry] Traversal error for {entry.url}: {exc}")
                continue

            sc = entry.selected_content

            for mod in discovered:
                # Skip synthetic container entries with no mod content
                if not mod.mod_id and not mod.components:
                    continue
                # AP mods: filter by game_id (2nd component of mod_id, e.g. "palworld")
                if mod.mod_id:
                    parts = mod.mod_id.split(".")
                    if game_id and len(parts) >= 2 and parts[1].lower() != game_id.lower():
                        continue
                    if not ContentFilter.includes_ap_mod(sc, mod.mod_id):
                        continue
                # Non-AP mods: filter by the registry's stored game_id
                else:
                    if game_id and entry.game_id and entry.game_id.lower() != game_id.lower():
                        continue
                    if not ContentFilter.includes_non_ap_mod(sc, mod.folder):
                        continue
                results.append(self._to_content_descriptor(mod, entry))

        return results

    def get_templates(self, game_id: str) -> list:
        """Return TemplateDescriptor list aggregated across all registries for game_id."""
        resolver = self._get_resolver()
        cache = self._get_cache()
        # path → [(repos: list[str], entry: RegistryDescriptor)]
        seen: dict[str, tuple[list[str], RegistryDescriptor]] = {}

        for entry in self.get_user_registries():
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception:
                continue
            for mod in discovered:
                for tpath in mod.templates_paths:
                    # tpath is like "Templates/Palworld"
                    game_dir = tpath.split("/")[-1] if "/" in tpath else tpath
                    if game_id and game_dir.lower() != game_id.lower():
                        continue
                    if not ContentFilter.includes_template(entry.selected_content, tpath):
                        continue
                    repo_key = f"{mod.owner}/{mod.repo}"
                    if tpath not in seen:
                        seen[tpath] = ([], entry)
                    existing_repos, _ = seen[tpath]
                    if repo_key not in existing_repos:
                        existing_repos.append(repo_key)

        results = []
        for tpath, (repos, reg_entry) in seen.items():
            results.append(_to_template_descriptor(tpath, repos, reg_entry))
        return results

    def get_other_content(self, game_id: str) -> list:
        """Return typed BinaryDescriptor list for UE4SS options from ue4ss.json in game registries.

        Traverses registries directly (not through get_mods) so that UE4SS options
        are gated only by their own ue4ss_option: keys — independent of whether the
        framework mod itself is in selected_content.

        K-8 Fix C/D: freshly built descriptors are cached to disk. On API failure,
        falls back to the last cached descriptor set for that registry + game.
        """
        from ..utils.registry.resolver import _is_framework_mod_id
        resolver = self._get_resolver()
        cache = self._get_cache()
        results = []
        for entry in self.get_user_registries():
            if game_id and entry.game_id and entry.game_id.lower() != game_id.lower():
                continue
            entry_descriptors: list = []
            try:
                discovered = resolver.traverse(entry.url, cache)
                for mod in discovered:
                    if not mod.ue4ss_info or not _is_framework_mod_id(getattr(mod, "mod_id", "")):
                        continue
                    for opt in mod.ue4ss_info.get("options", []):
                        raw_repo = opt.get("repo", "")
                        tag = opt.get("tag", "")
                        if not ContentFilter.includes_ue4ss(entry.selected_content, raw_repo, tag):
                            continue
                        entry_descriptors.append(_to_binary_descriptor(opt, entry))
                # K-8 Fix C: persist fresh descriptors to disk
                if entry_descriptors:
                    self._save_grb_descriptors(entry, game_id, entry_descriptors)
            except Exception as exc:
                self._host.log(
                    f"[registry] get_other_content traversal failed for {entry.url}: {exc} "
                    "— falling back to cached descriptors"
                )
                # K-8 Fix D: fall back to persisted descriptor cache on API failure
                entry_descriptors = self._load_grb_descriptors(entry, game_id)
            results.extend(entry_descriptors)
        return results

    def _grb_cache_dir(self, entry: RegistryDescriptor, game_id: str) -> "Path":
        """Return the per-registry+game cache directory for binary descriptors."""
        slug = f"{entry.repo.owner}+{entry.repo.repo}"
        return (
            Path.home() / ".apf_manager" / "cache" / "_registries"
            / slug / (game_id or "_global") / "ue4ss_options"
        )

    def _save_grb_descriptors(
        self, entry: RegistryDescriptor, game_id: str, descriptors: list
    ) -> None:
        """Persist typed binary descriptors to disk (K-8 Fix C)."""
        import hashlib
        from ..shared.data.pipeline_state import ContentSerializer
        cache_dir = self._grb_cache_dir(entry, game_id)
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            for desc in descriptors:
                # Use content_hash if available, otherwise derive from name + install_type
                _hash = getattr(getattr(desc, "tags", None), "content_hash", None)
                key = _hash or f"{desc.name}|{getattr(desc, 'install_type', '')}"
                safe_key = hashlib.sha256(key.encode()).hexdigest()[:16]
                dest = cache_dir / safe_key
                dest.mkdir(parents=True, exist_ok=True)
                ContentSerializer().save_cache(dest, desc)
        except Exception as exc:
            self._host.log(f"[registry] _save_grb_descriptors failed: {exc}")

    def _load_grb_descriptors(
        self, entry: RegistryDescriptor, game_id: str
    ) -> list:
        """Load persisted binary descriptors from disk (K-8 Fix D)."""
        from ..shared.data.pipeline_state import ContentSerializer
        cache_dir = self._grb_cache_dir(entry, game_id)
        results = []
        if not cache_dir.exists():
            return results
        for subdir in cache_dir.iterdir():
            if not subdir.is_dir():
                continue
            result = ContentSerializer().load_cache(subdir)
            if result:
                desc, _ = result
                results.append(desc)
        return results

    def invalidate_other_cache(self, owner: str, repo: str, game_id: str) -> None:
        """Delete the on-disk binary descriptor cache for a registry+game (K-8 Fix D).

        Called when the user clicks Refresh or re-adds a registry, forcing a fresh
        API load on the next get_other_content() call.
        """
        slug = f"{owner}+{repo}"
        cache_dir = (
            Path.home() / ".apf_manager" / "cache" / "_registries"
            / slug / (game_id or "_global") / "ue4ss_options"
        )
        try:
            if cache_dir.exists():
                shutil.rmtree(str(cache_dir))
        except Exception as exc:
            self._host.log(f"[registry] invalidate_other_cache failed: {exc}")

    def get_framework_candidates(self, game_id: str) -> list[FrameworkModCandidate]:
        """Return scored framework mod candidates from all registered registries."""
        from ..utils.registry.resolver import _is_framework_mod_id
        resolver = self._get_resolver()
        cache = self._get_cache()

        fw_pairs: list[tuple] = []  # (DiscoveredMod, RegistryDescriptor)
        for entry in self.get_user_registries():
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception:
                continue
            for mod in discovered:
                if _is_framework_mod_id(getattr(mod, "mod_id", "")):
                    fw_pairs.append((mod, entry))

        if not fw_pairs:
            return []

        scored = resolver.score_framework_candidates(
            [mod for mod, _ in fw_pairs], game_id,
        )
        disc_by_id = {mod.mod_id: (mod, entry) for mod, entry in fw_pairs}
        return [
            FrameworkModCandidate(
                entry=self._to_content_descriptor(
                    disc_by_id[disc.mod_id][0], disc_by_id[disc.mod_id][1]
                ),
                score=score,
                score_breakdown=bd,
                in_chain=True,
                ue4ss_info=disc.ue4ss_info,
            )
            for score, bd, disc in scored
            if disc.mod_id in disc_by_id
        ]

    def get_ue4ss_info(self, game_id: str) -> Optional[UE4SSInfo]:
        """
        Discover UE4SS installation options from user-registered registry data only.

        Returns None when no game-specific UE4SS info is found.
        Callers that need a bootstrap path should use UpdatesService.get_ue4ss_releases_for_content().
        """
        from ..utils.registry.resolver import _is_framework_mod_id
        resolver = self._get_resolver()
        cache = self._get_cache()
        for entry in self.get_user_registries():
            if game_id and entry.game_id and entry.game_id.lower() != game_id.lower():
                continue
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception:
                continue
            for mod in discovered:
                if mod.ue4ss_info and _is_framework_mod_id(getattr(mod, "mod_id", "")):
                    info = mod.ue4ss_info
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

    def get_staged(self) -> list:
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

    def get_mod_docs(self, entry) -> list[DocEntry]:
        docs = []
        readme_url = entry.docs.readme_url if getattr(entry, "docs", None) else ""
        if readme_url:
            source = getattr(entry, "source", None)
            owner = source.repo.owner if source else ""
            repo = source.repo.repo if source else ""
            folder = source.folder if source else ""
            docs.append(DocEntry(
                owner=owner,
                repo=repo,
                ref="HEAD",
                path=f"{folder}/README.md",
                raw_url=readme_url,
                title=f"{entry.name} — README",
                doc_type="mod",
            ))
        return docs

    def get_registry_docs(self, entry: RegistryDescriptor) -> list[DocEntry]:
        api = self._make_api(entry.repo.owner, entry.repo.repo)
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
                owner=entry.repo.owner,
                repo=entry.repo.repo,
                ref="HEAD",
                path="README.md",
                raw_url=root_readme["download_url"],
                title=f"{entry.repo.repo} — README",
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
                            owner=entry.repo.owner,
                            repo=entry.repo.repo,
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
    # Typed descriptor conversion
    # -----------------------------------------------------------------------

    def _to_content_descriptor(self, mod: "DiscoveredMod", entry: RegistryDescriptor):
        """Convert a DiscoveredMod to the appropriate typed ContentDescriptor subclass."""
        from ..utils.registry.resolver import _is_framework_mod_id
        source = RegistrySource(
            repo=entry.repo,
            registry_url=entry.url,
            folder=mod.folder,
            submodule_parent=(
                GitHubRepo.from_full_name(mod.submodule_of)
                if getattr(mod, "submodule_of", None) else None
            ),
        )
        components = ModComponents.from_lists(
            mod.components or [], mod.bp_pak_files or []
        )
        docs = DocInfo(readme_url=mod.readme_url or "")
        tags = ContentTags(
            is_framework=_is_framework_mod_id(mod.mod_id or ""),
            is_submodule=source.is_submodule,
        )
        name = mod.manifest.get("name") or mod.folder.split("/")[-1]
        version = mod.manifest.get("version", "")
        if mod.mod_id:
            parts = mod.mod_id.split(".")
            game_id = parts[1] if len(parts) >= 2 else ""
            if _is_framework_mod_id(mod.mod_id):
                return FrameworkModDescriptor(
                    name=name, version=version, game_id=game_id,
                    folder_name=mod.folder.split("/")[-1],
                    description=mod.manifest.get("description", ""),
                    author=mod.manifest.get("author", ""),
                    mod_id=mod.mod_id,
                    source=source, components=components, docs=docs, tags=tags,
                    capabilities_includes=mod.manifest.get("capabilities", {}).get("include", []),
                )
            return APModDescriptor(
                name=name, version=version, game_id=game_id,
                folder_name=mod.folder.split("/")[-1],
                description=mod.manifest.get("description", ""),
                author=mod.manifest.get("author", ""),
                mod_id=mod.mod_id,
                source=source, components=components, docs=docs, tags=tags,
                capabilities_includes=mod.manifest.get("capabilities", {}).get("include", []),
            )
        return ThirdPartyModDescriptor(
            name=name, version=version,
            game_id=entry.game_id,
            folder_name=mod.folder.split("/")[-1],
            description=mod.manifest.get("description", ""),
            author=mod.manifest.get("author", ""),
            source=source, components=components, docs=docs, tags=tags,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _get_cache(self) -> "RegistryCache":
        if self._cache is None:
            from ..utils.registry.cache import RegistryCache
            self._cache = RegistryCache()
        return self._cache

    def _get_resolver(self):
        if self._resolver is None:
            from ..utils.registry.resolver import RegistryResolver
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
        from ..utils.registry.resolver import _is_framework_mod_id
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

    def _get_existing_sc(self, url: str) -> Optional[list]:
        """Return the current selected_content stored for url, or None if not found."""
        for r in self._host.config.get_user_registries():
            if r.get("url") == url:
                return r.get("selected_content")
        return None

    def _make_api(self, owner: str, repo: str):
        from ....core.remote.github_api import GitHubAPI
        from ..utils.registry.resolver import _BUNDLED_PAT
        token_path = _BUNDLED_PAT if _BUNDLED_PAT.exists() else None
        return GitHubAPI(
            repo_owner=owner,
            repo_name=repo,
            token_file_path=token_path,
            on_status=self._on_status,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_sc_from_viewer_result(selected_mods, raw_selected_ids) -> Optional[list]:
    """Shared _finalize helper: build selected_content list from viewer result."""
    from ..utils.registry.resolver import _is_framework_mod_id
    if raw_selected_ids is None:
        return None
    sc: list = []
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
    return sc


def _to_template_descriptor(
    tpath: str, repos: list, entry: RegistryDescriptor
) -> TemplateDescriptor:
    """Build a TemplateDescriptor from a template path, contributing repo list, and registry entry."""
    first_repo = GitHubRepo.from_full_name(repos[0]) if repos else entry.repo
    conflict_sources = [GitHubRepo.from_full_name(r) for r in repos[1:]]
    game_dir = tpath.split("/")[-1] if "/" in tpath else tpath
    return TemplateDescriptor(
        name=game_dir,
        game_id=game_dir,
        template_path=tpath,
        source=RegistrySource(repo=first_repo, registry_url=entry.url, folder=tpath),
        tags=ContentTags(has_conflict=len(repos) > 1),
        conflict_sources=conflict_sources,
    )


def _to_binary_descriptor(opt: dict, entry: RegistryDescriptor) -> BinaryDescriptor:
    """Build a typed BinaryDescriptor from a ue4ss.json option dict and its registry entry."""
    import hashlib
    otype = opt.get("type", "manual")
    raw_repo = opt.get("repo", "")
    tag = opt.get("tag", "")
    owner, repo_name = raw_repo.split("/", 1) if "/" in raw_repo else ("", raw_repo)
    name = opt.get("note", "UE4SS")
    install_type = opt.get("install_type", "ue4ss")

    # K-11 Fix A: parse the optional 'docs' field (registry-relative path → full raw URL).
    # The docs field is a path relative to the REGISTRY repo root (e.g. "APFrameworkMod/setup.md").
    # We construct a full raw GitHub URL here because the path is registry-relative — this is
    # intentionally different from the K-3 bug, where an already-full URL was being re-wrapped.
    docs_path = opt.get("docs", "")
    docs = None
    if docs_path:
        raw_doc_url = (
            f"https://raw.githubusercontent.com/"
            f"{entry.repo.owner}/{entry.repo.repo}/HEAD/{docs_path}"
        )
        docs = DocInfo(readme_url=raw_doc_url)

    if otype == "github_release":
        fp = "|".join([owner, repo_name, tag, install_type, entry.repo.full_name, "github_release"])
        content_hash = hashlib.sha256(fp.encode()).hexdigest()[:20]
        return GithubReleaseBinary(
            name=name,
            install_type=install_type,
            source=ReleaseSource(
                repo=GitHubRepo(owner=owner, repo=repo_name),
                tag=tag,
                is_prerelease=opt.get("prerelease", False),
            ),
            registry_source=RegistrySource(repo=entry.repo, registry_url=entry.url, folder=""),
            tags=ContentTags(content_hash=content_hash),
            docs=docs,
        )
    elif otype == "external_url":
        return ExternalUrlBinary(
            name=name, install_type=install_type,
            url=opt.get("url", ""), note=name, docs=docs,
        )
    else:
        return ManualBinary(name=name, install_type=install_type, note=name, docs=docs)


def _ui(fn: Callable) -> None:
    """Schedule fn on the Kivy main thread."""
    from kivy.clock import Clock
    Clock.schedule_once(lambda dt: fn(), 0)
