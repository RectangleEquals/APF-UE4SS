"""DiscoveryMixin — mod/template/binary/UE4SS discovery for RegistryService."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ......core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from ....models.descriptors.types import RegistryDescriptor


class DiscoveryMixin:
    """Mixin for RegistryService: get_mods, get_templates, get_other_content, get_ue4ss_info."""

    # -----------------------------------------------------------------------
    # Mod / template / other discovery
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

        # Pre-warm docs cache so the viewer is fast on first open.
        threading.Thread(
            target=self._prefetch_docs_bg,
            args=(list(mods),),
            daemon=True,
        ).start()

        return mods

    def _prefetch_docs_bg(self, mods: list) -> None:
        """Background pre-fetch for all mod README files (no-op when cache is warm)."""
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
                except Exception as exc:
                    logger.warning(f"Prefetch doc failed for {url}: {exc}")
        except Exception as exc:
            logger.warning(f"_prefetch_docs_bg failed: {exc}")

    def _load_mods(self, game_id: str) -> list:
        from ....models.descriptors.filter import ContentFilter
        from ..descriptor_factory import to_content_descriptor
        resolver = self._get_resolver()
        cache = self._get_cache()
        results = []

        for entry in self.get_user_registries():
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception as exc:
                logger.error(f"Traversal error for {entry.url}: {exc}")
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
                results.append(to_content_descriptor(mod, entry, log_fn=self._host.log))

        return results

    def get_templates(self, game_id: str) -> list:
        """Return TemplateDescriptor list aggregated across all registries for game_id."""
        from ....models.descriptors.filter import ContentFilter
        from ..descriptor_factory import to_template_descriptor
        resolver = self._get_resolver()
        cache = self._get_cache()
        # path → [(repos: list[str], entry: RegistryDescriptor)]
        seen: dict[str, tuple[list[str], object]] = {}

        for entry in self.get_user_registries():
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception as exc:
                logger.warning(f"Traversal failed for {entry.url}: {exc}")
                continue
            for mod in discovered:
                for tpath in mod.templates_paths:
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
            results.append(to_template_descriptor(tpath, repos, reg_entry))
        return results

    def get_other_content(self, game_id: str) -> list:
        """Return typed BinaryDescriptor list for UE4SS options from ue4ss.json in game registries.

        K-8 Fix C/D: freshly built descriptors are cached to disk. On API failure,
        falls back to the last cached descriptor set for that registry + game.
        """
        from ..resolver import _is_framework_mod_id
        from ....models.descriptors.filter import ContentFilter
        from ..descriptor_factory import to_binary_descriptor
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
                        entry_descriptors.append(to_binary_descriptor(opt, entry))
                if entry_descriptors:
                    self._save_grb_descriptors(entry, game_id, entry_descriptors)
            except Exception as exc:
                logger.error(
                    f"get_other_content traversal failed for {entry.url}: {exc} "
                    "-- falling back to cached descriptors"
                )
                entry_descriptors = self._load_grb_descriptors(entry, game_id)
            results.extend(entry_descriptors)
        return results

    def _grb_cache_dir(self, entry, game_id: str) -> Path:
        """Return the per-registry+game cache directory for binary descriptors."""
        slug = f"{entry.repo.owner}+{entry.repo.repo}"
        return (
            Path.home() / ".apf_manager" / "cache" / "_registries"
            / slug / (game_id or "_global") / "ue4ss_options"
        )

    def _save_grb_descriptors(self, entry, game_id: str, descriptors: list) -> None:
        """Persist typed binary descriptors to disk (K-8 Fix C)."""
        import hashlib
        from ....models.state.pipeline import ContentSerializer
        cache_dir = self._grb_cache_dir(entry, game_id)
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            for desc in descriptors:
                _hash = getattr(getattr(desc, "tags", None), "content_hash", None)
                key = _hash or f"{desc.name}|{getattr(desc, 'install_type', '')}"
                safe_key = hashlib.sha256(key.encode()).hexdigest()[:16]
                dest = cache_dir / safe_key
                dest.mkdir(parents=True, exist_ok=True)
                ContentSerializer().save_cache(dest, desc)
        except Exception as exc:
            logger.error(f"_save_grb_descriptors failed: {exc}")

    def _load_grb_descriptors(self, entry, game_id: str) -> list:
        """Load persisted binary descriptors from disk (K-8 Fix D)."""
        from ....models.state.pipeline import ContentSerializer
        cache_dir = self._grb_cache_dir(entry, game_id)
        results = []
        if not cache_dir.exists():
            return results
        for subdir in cache_dir.iterdir():
            if not subdir.is_dir():
                continue
            result = ContentSerializer().load_cache(subdir, log_fn=self._host.log)
            if result:
                desc, _ = result
                results.append(desc)
        return results

    def invalidate_other_cache(self, owner: str, repo: str, game_id: str) -> None:
        """Delete the on-disk binary descriptor cache for a registry+game (K-8 Fix D)."""
        import shutil
        slug = f"{owner}+{repo}"
        cache_dir = (
            Path.home() / ".apf_manager" / "cache" / "_registries"
            / slug / (game_id or "_global") / "ue4ss_options"
        )
        try:
            if cache_dir.exists():
                shutil.rmtree(str(cache_dir))
        except Exception as exc:
            logger.warning(f"invalidate_other_cache failed: {exc}")

    def get_framework_candidates(self, game_id: str) -> list:
        """Return scored framework mod candidates from all registered registries."""
        from ..resolver import _is_framework_mod_id
        from ..descriptor_factory import to_content_descriptor
        resolver = self._get_resolver()
        cache = self._get_cache()

        fw_pairs: list[tuple] = []
        for entry in self.get_user_registries():
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception as exc:
                logger.warning(f"Traversal failed for {entry.url}: {exc}")
                continue
            for mod in discovered:
                if _is_framework_mod_id(getattr(mod, "mod_id", "")):
                    fw_pairs.append((mod, entry))

        if not fw_pairs:
            return []

        from . import FrameworkModCandidate  # late import; service is fully loaded at call time
        scored = resolver.score_framework_candidates(
            [mod for mod, _ in fw_pairs], game_id,
        )
        disc_by_id = {mod.mod_id: (mod, entry) for mod, entry in fw_pairs}
        return [
            FrameworkModCandidate(
                entry=to_content_descriptor(
                    disc_by_id[disc.mod_id][0], disc_by_id[disc.mod_id][1],
                    log_fn=self._host.log,
                ),
                score=score,
                score_breakdown=bd,
                in_chain=True,
                ue4ss_info=disc.ue4ss_info,
            )
            for score, bd, disc in scored
            if disc.mod_id in disc_by_id
        ]

    def get_ue4ss_info(self, game_id: str):
        """
        Discover UE4SS installation options from user-registered registry data only.

        Returns None when no game-specific UE4SS info is found.
        """
        from ..resolver import _is_framework_mod_id
        from . import UE4SSInfo  # late import; service is fully loaded at call time
        resolver = self._get_resolver()
        cache = self._get_cache()
        for entry in self.get_user_registries():
            if game_id and entry.game_id and entry.game_id.lower() != game_id.lower():
                continue
            try:
                discovered = resolver.traverse(entry.url, cache)
            except Exception as exc:
                logger.warning(f"Traversal failed for {entry.url}: {exc}")
                continue
            for mod in discovered:
                if mod.ue4ss_info and _is_framework_mod_id(getattr(mod, "mod_id", "")):
                    info = mod.ue4ss_info
                    return UE4SSInfo(
                        options=info.get("options", []),
                        docs=info.get("docs"),
                    )
        return None
