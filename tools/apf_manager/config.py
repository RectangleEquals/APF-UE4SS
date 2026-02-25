"""
APF Manager — configuration and state dataclasses.

APFConfig: user preferences (mode, game_root, repo URL, dev paths). Persisted to .apf_manager_config.json.
APFState:  deployment tracking (which mods are installed, last deploy time). Persisted to .apf_state.json.

All runtime paths (target_install, logicmods_dir, ue4ss_dir) are derived by UE4SSDetector
from game_root at startup — never stored in config.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Config and state files live alongside the package so they don't pollute the project root.
_PACKAGE_DIR = Path(__file__).parent
CONFIG_FILE = _PACKAGE_DIR / ".apf_manager_config.json"
STATE_FILE = _PACKAGE_DIR / ".apf_state.json"


# ---------------------------------------------------------------------------
# APFConfig
# ---------------------------------------------------------------------------

@dataclass
class APFConfig:
    """User preferences. Loaded/saved to .apf_manager_config.json."""

    mode: str = "player"
    """'player' — download from GitHub releases; 'dev' — use local source + build dir."""

    game_root: str = ""
    """Top-level game folder (e.g. E:/SteamLibrary/steamapps/common/Palworld).
    UE4SSDetector recursively scans from here to find binaries_dir, mods_dir, content_paks_dir, etc."""

    repo_api_url: str = ""
    """GitHub API base for the release repo (e.g. https://api.github.com/repos/owner/repo).
    No URL is hardcoded in the source — must be configured by the user."""

    # Dev-mode only -----------------------------------------------------------
    source_project: str = ""
    """Root of the AP Framework source project. Defaults to the grandparent of this package
    (i.e. project root when running from the repo). Only used in dev mode."""

    build_dir: str = ""
    """Path to compiled binaries (APFrameworkCore.dll, APClientLib.dll, etc.).
    Defaults to source_project/build/Release/bin. Only used in dev mode."""

    # -------------------------------------------------------------------------

    def save(self) -> None:
        CONFIG_FILE.write_text(json.dumps(self.__dict__, indent=4))

    @classmethod
    def load(cls) -> APFConfig:
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text())
                # Only use keys that exist in the dataclass to be forward-compatible.
                known = {f.name for f in cls.__dataclass_fields__.values()}
                filtered = {k: v for k, v in raw.items() if k in known}
                return cls(**filtered)
            except Exception:
                pass
        # Apply sensible defaults for source_project and build_dir.
        obj = cls()
        obj._apply_defaults()
        return obj

    def _apply_defaults(self) -> None:
        if not self.source_project:
            self.source_project = str(_PACKAGE_DIR.parent.parent)
        if not self.build_dir:
            self.build_dir = str(Path(self.source_project) / "build" / "Release" / "bin")

    def resolve(self) -> APFConfig:
        """Return a copy with all defaults applied (non-mutating)."""
        import copy
        obj = copy.copy(self)
        obj._apply_defaults()
        return obj


# ---------------------------------------------------------------------------
# APFState — installation tracking
# ---------------------------------------------------------------------------

@dataclass
class InstalledModInfo:
    version: str = "unknown"
    deployed_at: str = ""


@dataclass
class APFState:
    """Deployment history. Loaded/saved to .apf_state.json."""

    last_deploy: str = ""
    installed_mods: dict[str, InstalledModInfo] = field(default_factory=dict)

    def save(self) -> None:
        data = {
            "last_deploy": self.last_deploy,
            "installed_mods": {k: v.__dict__ for k, v in self.installed_mods.items()},
        }
        STATE_FILE.write_text(json.dumps(data, indent=4))

    @classmethod
    def load(cls) -> APFState:
        if STATE_FILE.exists():
            try:
                raw = json.loads(STATE_FILE.read_text())
                state = cls()
                state.last_deploy = raw.get("last_deploy", "")
                for k, v in raw.get("installed_mods", {}).items():
                    state.installed_mods[k] = InstalledModInfo(**v)
                return state
            except Exception:
                pass
        return cls()
