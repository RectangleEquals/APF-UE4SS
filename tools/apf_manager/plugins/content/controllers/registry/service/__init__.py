"""
RegistryService — manages user registries, mod discovery, staging, and install.

Service ID: "registry" — registered in plugins/mods/__init__.py.

Fix A: RegistryViewer and Clock.schedule_once removed entirely from this layer.
All callbacks (on_done, on_viewer_requested) are called directly; the tab controller
is responsible for scheduling any Kivy-thread work via Clock.schedule_once.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional, Callable, TYPE_CHECKING

from .discovery import DiscoveryMixin
from .staging import StagingMixin
from .sharing import SharingMixin

from ....models.descriptors.base import GitHubRepo, RegistrySource
from ....models.descriptors.types import RegistryDescriptor

if TYPE_CHECKING:
    from ......core.config import GameProfile
    from ......core.plugin_host import PluginHost
    from ..resolver import DiscoveredMod
    from ..cache import RegistryCache


# ---------------------------------------------------------------------------
# Public dataclasses returned by this service
# ---------------------------------------------------------------------------

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

class RegistryService(DiscoveryMixin, StagingMixin, SharingMixin):
    """
    Manages user-added registries, traversal caching, mod staging, and install.

    Registered as the "registry" service by plugins/mods/__init__.py.
    Inherits modular mixin slices: DiscoveryMixin, StagingMixin, SharingMixin.
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
        self._staged: list[str] = []

        # Rate-limit callbacks — set by registries_tab via set_rate_limit_callbacks()
        self._on_rate_limit_cb: Optional[Callable] = None
        self._on_search_rate_limit_cb: Optional[Callable] = None

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
    # Registry management (Fix A: no RegistryViewer, no _ui(), no Clock)
    # -----------------------------------------------------------------------

    def get_user_registries(self, game_id: str = "") -> list[RegistryDescriptor]:
        """Return RegistryDescriptor objects for user-added registry URLs."""
        from ..resolver import parse_github_url
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

    def add_registry(
        self,
        url: str,
        on_done: Callable[[bool, str], None],
        on_viewer_requested: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """
        Validate and add a registry URL.
        Runs traversal on a background thread; calls on_done(success, msg) directly.
        If the viewer is needed and on_viewer_requested is provided, calls it with
        a dict of viewer kwargs (repo_url, game_id, traversal_result, on_confirm,
        on_cancel, …). The tab controller wraps this in Clock.schedule_once.
        """
        from ..resolver import parse_github_url
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
                on_done(False, f"Traversal failed: {exc}")
                return

            has_real_mods = any(m.mod_id for m in mods)
            has_templates = any(m.templates_paths for m in mods)
            if not has_real_mods and not has_templates:
                on_done(
                    False,
                    "No AP mods or templates found — is this a valid APF registry?"
                )
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

            # Reject if registry targets a different game than the current profile.
            current_game_id = self._get_game_id() or ""
            if current_game_id and derived_game_id and derived_game_id != current_game_id:
                on_done(
                    False,
                    f"No content found for '{current_game_id}' — this registry targets a different game."
                )
                return

            mod_items = [m for m in mods if m.mod_id]
            tpl_items = [tp for m in mods for tp in m.templates_paths]
            content_count = len(mod_items) + len(tpl_items)

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
                self._host.log(
                    f"[registry] _build_sc_from_viewer_result: "
                    f"selected_mods={len(selected_mods)} → sc={sc}"
                )
                self._host.config.add_user_registry(url, game_id=derived_game_id,
                                                     selected_content=sc)
                self._invalidate_mods_cache()
                on_done(True, f"Registry added — {summary} found.")

            if content_count > 1 and on_viewer_requested:
                game_id_for_viewer = current_game_id or derived_game_id
                on_viewer_requested({
                    "repo_url": url,
                    "game_id": game_id_for_viewer,
                    "traversal_result": mods,
                    "existing_mod_ids": existing_mod_ids,
                    "initial_selected_content": self._get_existing_sc(url),
                    "on_confirm": _finalize,
                    "on_cancel": lambda: on_done(False, "Cancelled."),
                })
            else:
                _finalize(mods)

        threading.Thread(target=_bg, daemon=True).start()

    def add_registry_with_viewer(
        self,
        url: str,
        game_id: str,
        on_done: Callable[[bool, str], None],
        on_viewer_requested: Optional[Callable[[dict], None]] = None,
    ) -> None:
        """
        Like add_registry(), but always opens the Repo Viewer (unless blacklisted).
        Passes the full folder tree to the viewer so the sidebar shows real structure.
        """
        from ..resolver import parse_github_url
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
                on_done(False, f"Traversal failed: {exc}")
                return

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
                    on_done(
                        False,
                        f"This registry has no content for '{current_game_id}'. "
                        f"It may be intended for a different game."
                    )
                    return

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
            except Exception as exc:
                self._host.log(f"[registry] WARN: get_folder_tree failed for {url}: {exc}")
                folder_tree = None

            def _finalize(selected_mods, raw_selected_ids=None):
                ap_count     = sum(1 for m in selected_mods if m.mod_id)
                non_ap_count = sum(1 for m in selected_mods if not m.mod_id)
                parts = [f"{ap_count} AP mod(s)"] if ap_count else []
                if non_ap_count:
                    parts.append(f"{non_ap_count} non-AP mod(s)")
                summary = ", ".join(parts) if parts else "no mods"
                sc = _build_sc_from_viewer_result(selected_mods, raw_selected_ids)
                self._host.log(
                    f"[registry] _build_sc_from_viewer_result: "
                    f"selected_mods={len(selected_mods)} → sc={sc}"
                )
                self._host.config.add_user_registry(url, game_id=derived_game_id,
                                                     selected_content=sc)
                self._invalidate_mods_cache()
                on_done(True, f"Registry added — {summary} found.")

            if on_viewer_requested:
                on_viewer_requested({
                    "repo_url": url,
                    "game_id": derived_game_id or game_id,
                    "traversal_result": mods,
                    "folder_tree": folder_tree,
                    "existing_mod_ids": existing_mod_ids,
                    "initial_selected_content": self._get_existing_sc(url),
                    "on_confirm": _finalize,
                    "on_cancel": lambda: on_done(False, "Cancelled."),
                })
            else:
                # No viewer callback — auto-finalize with all mods
                _finalize(mods)

        threading.Thread(target=_bg, daemon=True).start()

    def remove_registry(self, url: str) -> None:
        """Remove a user registry URL and invalidate the mods cache."""
        self._host.config.remove_user_registry(url)
        self._invalidate_mods_cache()

    def refresh_all(self, on_done: Optional[Callable] = None) -> None:
        """Re-traverse all registered repos (bypass traversal cache), then call on_done directly."""
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
                on_done()

        threading.Thread(target=_bg, daemon=True).start()

    def is_blacklisted(self, owner: str, repo: str) -> bool:
        return self._get_resolver().is_blacklisted(owner, repo)

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
        except Exception as exc:
            self._host.log(f"[registry] WARN: list_contents failed for {entry.repo.full_name}: {exc}")
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
            except Exception as exc:
                self._host.log(
                    f"[registry] WARN: list_contents docs/ failed for {entry.repo.full_name}: {exc}"
                )
        return docs

    # -----------------------------------------------------------------------
    # Capabilities (for DevTools CI)
    # -----------------------------------------------------------------------

    def build_capabilities(self, game_id: str) -> dict:
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            return mods_svc.build_capabilities()
        return {}

    def get_templates_dirs(self, game_id: str) -> list:
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            return mods_svc._resolve_templates_dirs()
        return []

    # -----------------------------------------------------------------------
    # Rate-limit callbacks (set by tab controller)
    # -----------------------------------------------------------------------

    def set_rate_limit_callbacks(
        self,
        on_rate_limit: Optional[Callable],
        on_search_rate_limit: Optional[Callable],
    ) -> None:
        """Called by registries tab controller to wire UI-layer rate-limit dialogs."""
        self._on_rate_limit_cb = on_rate_limit
        self._on_search_rate_limit_cb = on_search_rate_limit

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _on_status(self, level: str, msg: str) -> None:
        """Status callback from RegistryResolver. No Clock — caller schedules if needed."""
        if level == "rate_limit_exceeded":
            if self._on_rate_limit_cb:
                self._on_rate_limit_cb(msg)
            else:
                self._host.log(f"[registry] WARN: GitHub rate limit reached: {msg}")
            return
        if level == "rate_limit_exceeded_search":
            if self._on_search_rate_limit_cb:
                self._on_search_rate_limit_cb(msg)
            else:
                self._host.log(f"[registry] WARN: GitHub search rate limit reached: {msg}")
            return
        if level == "debug":
            self._host.log(f"[registry] {msg}")
            return
        self._host.log(f"[registry] [{level.upper()}] {msg}")

    def _invalidate_mods_cache(self) -> None:
        with self._lock:
            self._mods_cache = []
            self._mods_cache_game_id = ""

    def _get_game_id(self) -> Optional[str]:
        """
        Derive the game_id string for registry filtering.

        Priority:
          1. Installed framework mod's mod_id (e.g. 'archipelago.palworld.framework' → 'palworld')
          2. Game profile display name, normalised
        """
        from ..resolver import _is_framework_mod_id
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

    def _get_cache(self) -> "RegistryCache":
        if self._cache is None:
            from ..cache import RegistryCache
            self._cache = RegistryCache()
        return self._cache

    def _get_resolver(self):
        if self._resolver is None:
            from ..resolver import RegistryResolver
            self._resolver = RegistryResolver(on_status=self._on_status)
        return self._resolver

    def _make_api(self, owner: str, repo: str):
        from ......core.remote.github_api import GitHubAPI
        from ..resolver import _BUNDLED_PAT
        token_path = _BUNDLED_PAT if _BUNDLED_PAT.exists() else None
        return GitHubAPI(
            repo_owner=owner,
            repo_name=repo,
            token_file_path=token_path,
            on_status=self._on_status,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _build_sc_from_viewer_result(selected_mods, raw_selected_ids) -> Optional[list]:
    """Build selected_content list from viewer result."""
    from ..resolver import _is_framework_mod_id
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
