"""base_zip_controller.py — Abstract base for zip content detection controllers."""
from __future__ import annotations

import zipfile
from typing import Optional, TYPE_CHECKING

from .content import BaseContentController

if TYPE_CHECKING:
    from .install import BaseInstallController


class BaseZipFileController(BaseContentController):
    """
    Abstract base for zip content detection.

    Subclasses override classify() to inspect the ZipFile TOC and store the
    detected layout variant in self._detected_layout. create_install_controller()
    then returns the matching concrete BaseInstallController subclass.

    classify() is called once per zip by DeployService._find_zip_controller().
    create_install_controller() reads the stored _detected_layout state — the
    zip is never re-opened.
    """

    def __init__(self, content=None) -> None:
        super().__init__(content)
        self._detected_layout: Optional[str] = None

    def classify(self, zf: zipfile.ZipFile) -> bool:
        """
        Inspect zf TOC, store detected layout in self._detected_layout.
        Return True if this controller handles the given zip; False otherwise.
        """
        raise NotImplementedError

    def create_install_controller(self) -> "BaseInstallController":
        """
        Return a concrete BaseInstallController for the detected layout.
        Must only be called after a successful classify() call.
        """
        raise NotImplementedError
