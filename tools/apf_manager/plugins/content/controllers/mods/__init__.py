"""controllers/mods — re-exports ModService and key symbols for clean plugin imports."""
from .service import ModService, ModInfo, _FRAMEWORK_MOD_RE, _SCAN_EXCLUDE

__all__ = ["ModService", "ModInfo", "_FRAMEWORK_MOD_RE", "_SCAN_EXCLUDE"]
