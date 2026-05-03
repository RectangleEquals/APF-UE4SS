"""
controllers — modular content deployment controller hierarchy.

All content-type-specific zip detection and deployment logic lives here.
DeployService delegates to these controllers via _zip_controller_classes()
and _dispatch_zip() — it contains no layout-specific logic itself.

To support a new content type or layout variant:
  1. Subclass BaseZipFileController — implement classify() to store _detected_layout
  2. Subclass BaseInstallController (or an existing abstract subclass)
  3. Add the new zip controller class to DeployService._zip_controller_classes()
  Never add if/elif layout branches to deploy_service.py directly.
"""
from .base_content_controller import BaseContentController
from .base_zip_controller import BaseZipFileController
from .base_install_controller import BaseInstallController
from .ue4ss_zip_controller import UE4SSZipFileController
from .ue4ss_install_controller import (
    UE4SSInstallController,
    UE4SSOfficialInstallController,
    UE4SSCustomInstallController,
)
from .framework_zip_controller import FrameworkZipFileController
from .framework_install_controller import FrameworkInstallController
from .blueprint_pak_zip_controller import BlueprintPakZipFileController
from .blueprint_pak_install_controller import BlueprintPakInstallController

__all__ = [
    "BaseContentController",
    "BaseZipFileController",
    "BaseInstallController",
    "UE4SSZipFileController",
    "UE4SSInstallController",
    "UE4SSOfficialInstallController",
    "UE4SSCustomInstallController",
    "FrameworkZipFileController",
    "FrameworkInstallController",
    "BlueprintPakZipFileController",
    "BlueprintPakInstallController",
]
