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
        Scan mods_dir for all folders containing framework_config.json +
        manifest.json whose mod_id matches 'archipelago.<game_id>.framework'.

        Returns:
          []       — framework mod not installed
          [path]   — exactly one found (normal state)
          [p1, p2] — conflict: multiple framework mods present
        """
        import json
        import re
        _FRAMEWORK_MOD_RE = re.compile(r"^archipelago\.[a-z0-9_]+\.framework$")
        results: list[Path] = []
        if not self._mods_dir or not self._mods_dir.is_dir():
            logger.debug(
                "[capabilities] Framework mod scan skipped: mods_dir unavailable (%s)",
                self._mods_dir,
            )
            return results
        for entry in sorted(self._mods_dir.iterdir()):
            if not entry.is_dir():
                continue
            cfg_path = entry / "framework_config.json"
            if not cfg_path.exists():
                continue
            manifest_path = entry / "manifest.json"
            if not manifest_path.exists():
                logger.debug(
                    "[capabilities] %s has framework_config.json but no manifest.json — skipping",
                    entry.name,
                )
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                mid = raw.get("mod_id", "")
                if _FRAMEWORK_MOD_RE.match(mid):
                    results.append(entry)
                    logger.info(
                        "[capabilities] Framework mod found: %s (mod_id=%r)", entry.name, mid
                    )
                else:
                    logger.debug(
                        "[capabilities] %s has framework_config.json but mod_id %r "
                        "does not match framework pattern — skipping",
                        entry.name, mid,
                    )
            except Exception as exc:
                logger.warning("Failed to read manifest at %s: %s", manifest_path, exc)
        if not results:
            logger.debug(
                "[capabilities] No framework mod found in %s (scanned %d dirs)",
                self._mods_dir,
                sum(1 for e in self._mods_dir.iterdir() if e.is_dir()),
            )
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
