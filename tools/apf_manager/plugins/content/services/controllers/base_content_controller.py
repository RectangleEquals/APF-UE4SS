"""base_content_controller.py — Abstract base for all content pipeline controllers."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ...shared.data.content_base import ContentDescriptor


class BaseContentController:
    """
    Abstract base for all content pipeline controllers.

    Holds an optional ContentDescriptor, which subclasses may use for
    content-type-aware decisions during detection or deployment.
    """

    def __init__(self, content: "Optional[ContentDescriptor]" = None) -> None:
        self.content = content
