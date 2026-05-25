"""ModCapabilitiesMixin — capabilities builder + framework mod dir for ModService."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ......core.controllers.logging.manager import APFLogManager

logger = APFLogManager.get_logger(__name__)


class ModCapabilitiesMixin:
    """Mixin for ModService: build_capabilities, framework mod directory helpers."""

    def build_capabilities(
        self,
        mods=None,
        game: str = "",
        strict: bool = False,
    ) -> dict:
        """
        Build aggregated capabilities from AP mods.
        `game` should be the actual game name (e.g. "Palworld") used as the
        Templates/<game>/ subdirectory name. Falls back to profile game_id.
        """
        from ....models.mods.capabilities import CapabilitiesBuilder
        if mods is None:
            mods = self.get_ap_mods()
        game_name = game or (self._game_id or "")
        templates_dirs = self._resolve_templates_dirs(game_name)
        return CapabilitiesBuilder().from_mod_infos(
            mods, game=game_name, templates_dirs=templates_dirs, strict=strict
        )

    # -----------------------------------------------------------------------
    # Framework mod — content-based detection (mirrors ap_path_util.cpp)
    # -----------------------------------------------------------------------

    def _find_framework_mod_dirs(self) -> list[Path]:
        """
        Scan mods_dir for all folders whose manifest.json mod_id matches
        'archipelago.<game_id>.framework'.

        Result is cached until invalidated by rescan() or on_game_changed() to
        avoid repeated disk scans within a single UI refresh cycle.

        framework_config.json is a user-preferences file created by the
        Configure screen (or manually).  Its absence means the user has not
        configured the framework yet — not that it is uninstalled — so we do
        not gate on it.  We log its presence for diagnostics only.

        Returns:
          []       — framework mod not installed
          [path]   — exactly one found (normal state)
          [p1, p2] — conflict: multiple framework mods present
        """
        cached = getattr(self, "_framework_dirs_cache", None)
        if cached is not None:
            return cached

        import json
        import re
        _FRAMEWORK_MOD_RE = re.compile(r"^archipelago\.[a-z0-9_]+\.framework$")
        results: list[Path] = []
        if not self._mods_dir or not self._mods_dir.is_dir():
            logger.debug(
                "[capabilities] Framework mod scan skipped: mods_dir unavailable (%s)",
                self._mods_dir,
            )
            self._framework_dirs_cache: list = results
            return results
        for entry in sorted(self._mods_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                mid = raw.get("mod_id", "")
                if not _FRAMEWORK_MOD_RE.match(mid):
                    continue
                configured = (entry / "framework_config.json").exists()
                results.append(entry)
                logger.info(
                    "[capabilities] Framework mod found: %s (mod_id=%r, configured=%s)",
                    entry.name, mid, configured,
                )
            except Exception as exc:
                logger.warning("[capabilities] Failed to read manifest at %s: %s", manifest_path, exc)
        if not results:
            logger.debug(
                "[capabilities] No framework mod found in %s (scanned %d dirs)",
                self._mods_dir,
                sum(1 for e in self._mods_dir.iterdir() if e.is_dir()),
            )
        self._framework_dirs_cache = results
        return results

    def get_framework_mod_dir(self) -> Optional[Path]:
        """Return the unique framework mod directory, or None if absent or conflicted."""
        found = self._find_framework_mod_dirs()
        return found[0] if len(found) == 1 else None

    def get_framework_mod_conflict(self) -> list[Path]:
        """Return multiple paths when more than one framework mod is deployed (conflict state)."""
        found = self._find_framework_mod_dirs()
        return found if len(found) > 1 else []

    def _resolve_templates_dirs(self, game_name: str = "") -> list[Path]:
        """
        Return [<framework_mod>/Templates/<game_name>/] if the framework mod is
        deployed and the game-level template dir exists.
        """
        if not game_name:
            return []
        fw_dir = self.get_framework_mod_dir()
        if not fw_dir:
            return []
        game_dir = fw_dir / "Templates" / game_name
        return [game_dir] if game_dir.is_dir() else []
