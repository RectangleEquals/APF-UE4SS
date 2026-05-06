"""base_install_controller.py — Abstract base for content installation controllers."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, TYPE_CHECKING

from .content import BaseContentController

if TYPE_CHECKING:
    from .zip import BaseZipFileController


class BaseInstallController(BaseContentController):
    """
    Abstract base for content installation.

    Holds a back-reference to the BaseZipFileController that created this
    instance, available for any layout queries needed at deploy time.
    """

    def __init__(
        self,
        content=None,
        zip_ctrl: "Optional[BaseZipFileController]" = None,
    ) -> None:
        super().__init__(content)
        self._zip_ctrl = zip_ctrl

    def deploy(
        self,
        zip_path: Path,
        platform_dir: Path,
        logicmods_dir: Optional[Path] = None,
    ) -> None:
        """Deploy content from zip_path to the appropriate target directory."""
        raise NotImplementedError

    def undeploy(self, record, platform_dir: Path) -> None:
        """Remove previously deployed content described by record."""
        raise NotImplementedError
