"""controllers/deploy — re-exports DeployService for clean plugin imports."""
from .service import DeployService

__all__ = ["DeployService"]
