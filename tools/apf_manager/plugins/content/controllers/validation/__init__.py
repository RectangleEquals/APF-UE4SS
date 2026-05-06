"""controllers/validation — re-exports ValidationService for clean plugin imports."""
from .service import ValidationService, ValidationResult

__all__ = ["ValidationService", "ValidationResult"]
