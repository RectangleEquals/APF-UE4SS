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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

# Bundled PAT lives alongside the docs_viewer plugin
_BUNDLED_PAT = Path(__file__).parent.parent / "docs_viewer" / ".github_token"

# Blacklist is fetched from this repo's own source tree (never cached)
_BLACKLIST_OWNER = "RectangleEquals"
_BLACKLIST_REPO  = "APF-UE4SS"
_BLACKLIST_PATH  = "tools/apf_manager/data/blacklist.json"

_GITHUB_URL_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s.]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# DiscoveredMod — result of traversal
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredMod:
    owner: str
    repo: str
    folder: str          # subfolder path within the repo
    manifest: dict       # raw manifest.json content
    mod_id: str          # manifest["mod_id"]
    readme_url: str = ""
    ue4ss_info: Optional[dict] = None      # parsed ue4ss.json (framework mod repos only)
    templates_paths: list = field(default_factory=list)  # e.g. ["Templates/Palworld"]


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
                return [DiscoveredMod(**d) for d in raw]
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
                continue

            manifest_text = api.fetch_text(manifest_entry["download_url"])
            if not manifest_text:
                continue
            try:
                manifest = json.loads(manifest_text)
            except Exception:
                continue
            if not manifest.get("mod_id"):
                continue  # Not an AP Framework mod

            readme_url = ""
            readme_entry = next(
                (e for e in sub_contents
                 if e["name"].lower() in ("readme.md", "readme.txt", "readme")),
                None,
            )
            if readme_entry and readme_entry.get("download_url"):
                readme_url = readme_entry["download_url"]

            # Attach ue4ss_info only to the framework mod in this repo
            mod_ue4ss = ue4ss_info if manifest["mod_id"].endswith(".framework") else None

            mods.append(DiscoveredMod(
                owner=owner,
                repo=repo,
                folder=folder_path,
                manifest=manifest,
                mod_id=manifest["mod_id"],
                readme_url=readme_url,
                ue4ss_info=mod_ue4ss,
                templates_paths=templates_paths,
            ))

        # Follow submodules recursively
        for entry in contents:
            if entry.get("type") != "submodule":
                continue
            sub_url = entry.get("submodule_git_url") or entry.get("git_url", "")
            if not sub_url:
                continue
            sub_mods = self.traverse(sub_url, cache, visited, depth + 1)
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
                        # Attach to any framework mod in this repo that lacks ue4ss_info
                        for mod in mods:
                            if mod.mod_id.endswith(".framework") and not mod.ue4ss_info:
                                mod.ue4ss_info = synth_ue4ss
            mods.extend(sub_mods)

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
                    }
                    for m in mods
                ]
                cache.set(cache_key, json.dumps(serialisable))
            except Exception:
                pass

        return mods

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
        if results is not None:
            cache.set(cache_key, json.dumps(results))
        return results or []

    def search_github_core(self, game_id: str) -> list[dict]:
        """
        Search for repos tagged apf-ue4ss-registry-{game_id}-core.
        NOT cached — used for targeted UE4SS discovery.
        """
        return self._call_search_api(f"apf-ue4ss-registry-{game_id}-core") or []

    def _call_search_api(self, topic: str) -> Optional[list[dict]]:
        import httpx
        token = self._load_bundled_token()
        headers = {
            "User-Agent": "APFManager/1.0",
            "Accept": "application/vnd.github+json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = httpx.get(
                "https://api.github.com/search/repositories",
                params={"q": f"topic:{topic}", "per_page": 30},
                headers=headers,
                timeout=15,
            )
            resp.raise_for_status()
            results = []
            for item in resp.json().get("items", []):
                pushed_at = item.get("pushed_at", "")
                try:
                    dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
                    days = (datetime.now(timezone.utc) - dt).days
                except Exception:
                    days = 999
                results.append({
                    "owner": item["owner"]["login"],
                    "repo": item["name"],
                    "stars": item.get("stargazers_count", 0),
                    "description": item.get("description", ""),
                    "html_url": item.get("html_url", ""),
                    "last_push_days": days,
                })
            return results
        except Exception as exc:
            self._on_status("warn", f"GitHub search failed: {exc}")
            return None

    # -----------------------------------------------------------------------
    # Blacklist
    # -----------------------------------------------------------------------

    def fetch_blacklist(self) -> set[str]:
        """
        Fetch blacklist.json live from the APF repo.  Never cached.
        Result held in memory for the session.
        """
        if self._blacklist_cache is not None:
            return self._blacklist_cache

        token = self._load_bundled_token()
        raw_url = (
            f"https://raw.githubusercontent.com/{_BLACKLIST_OWNER}/"
            f"{_BLACKLIST_REPO}/main/tools/apf_manager/data/blacklist.json"
        )
        import httpx
        headers = {"User-Agent": "APFManager/1.0"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = httpx.get(raw_url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._blacklist_cache = {r.lower() for r in data.get("repos", [])}
        except Exception:
            self._blacklist_cache = set()
        return self._blacklist_cache

    def is_blacklisted(self, owner: str, repo: str) -> bool:
        bl = self.fetch_blacklist()
        return f"{owner}/{repo}".lower() in bl

    def invalidate_blacklist_cache(self) -> None:
        """Force a fresh blacklist fetch on next check."""
        self._blacklist_cache = None

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
