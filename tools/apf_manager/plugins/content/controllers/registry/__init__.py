"""controllers/registry — re-exports RegistryService for clean plugin imports."""
from .service import RegistryService
from .service import DocEntry, FrameworkModCandidate, UE4SSInfo, RegistryError

__all__ = ["RegistryService", "DocEntry", "FrameworkModCandidate", "UE4SSInfo", "RegistryError"]
