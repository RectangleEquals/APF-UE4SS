"""
Public cross-plugin API surface for plugins/content.

All content data types are re-exported here so that other plugins can import
from the stable surface (plugins.content.shared) rather than the internal
sub-package path (plugins.content.shared.data.*).

Example:
    from ..content.shared import GithubReleaseBinary, ContentAsset, InstallStateManager
"""

from .data import (
    # Primitive / composition types
    ContentDescriptor,
    GitHubRepo,
    RegistrySource,
    ReleaseSource,
    ManualSource,
    ModComponents,
    DocInfo,
    DependencySpec,
    ContentAsset,
    ContentTags,
    # Concrete content descriptor subclasses
    ModDescriptor,
    ThirdPartyModDescriptor,
    APModDescriptor,
    FrameworkModDescriptor,
    TemplateDescriptor,
    BinaryDescriptor,
    GithubReleaseBinary,
    ExternalUrlBinary,
    ManualBinary,
    DocDescriptor,
    RegistryDescriptor,
    # Persistence
    ContentSerializer,
    InstallRecord,
    CURRENT_SCHEMA_VERSION,
    # Data-layer utilities
    ContentFilter,
    InstallStateManager,
)

__all__ = [
    "ContentDescriptor",
    "GitHubRepo",
    "RegistrySource",
    "ReleaseSource",
    "ManualSource",
    "ModComponents",
    "DocInfo",
    "DependencySpec",
    "ContentAsset",
    "ContentTags",
    "ModDescriptor",
    "ThirdPartyModDescriptor",
    "APModDescriptor",
    "FrameworkModDescriptor",
    "TemplateDescriptor",
    "BinaryDescriptor",
    "GithubReleaseBinary",
    "ExternalUrlBinary",
    "ManualBinary",
    "DocDescriptor",
    "RegistryDescriptor",
    "ContentSerializer",
    "InstallRecord",
    "CURRENT_SCHEMA_VERSION",
    "ContentFilter",
    "InstallStateManager",
]