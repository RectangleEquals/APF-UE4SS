from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from .content_base import (
    ContentDescriptor, GitHubRepo, RegistrySource, ReleaseSource, ManualSource,
    ModComponents, DocInfo, DependencySpec, ContentAsset, ContentTags,
)


@dataclass
class ModDescriptor(ContentDescriptor):
    folder_name: str = ""
    description: str = ""
    author: str = ""
    source: Optional[RegistrySource] = None
    components: Optional[ModComponents] = None
    docs: Optional[DocInfo] = None
    tags: Optional[ContentTags] = None


@dataclass
class ThirdPartyModDescriptor(ModDescriptor):
    content_type: str = "third_party_mod"


@dataclass
class APModDescriptor(ModDescriptor):
    content_type: str = "ap_mod"
    mod_id: str = ""
    dependencies: list = field(default_factory=list)
    capabilities_includes: list = field(default_factory=list)


@dataclass
class FrameworkModDescriptor(APModDescriptor):
    content_type: str = "framework_mod"
    ue4ss_recommendations: list = field(default_factory=list)


@dataclass
class TemplateDescriptor(ContentDescriptor):
    content_type: str = "template"
    template_path: str = ""
    source: Optional[RegistrySource] = None
    docs: Optional[DocInfo] = None
    tags: Optional[ContentTags] = None
    conflict_sources: list = field(default_factory=list)


@dataclass
class BinaryDescriptor(ContentDescriptor):
    install_type: str = ""
    assets: list = field(default_factory=list)
    docs: Optional[DocInfo] = None
    tags: Optional[ContentTags] = None


@dataclass
class GithubReleaseBinary(BinaryDescriptor):
    content_type: str = "github_release_binary"
    source: Optional[ReleaseSource] = None
    registry_source: Optional[RegistrySource] = None


@dataclass
class ExternalUrlBinary(BinaryDescriptor):
    content_type: str = "external_url_binary"
    url: str = ""
    note: str = ""


@dataclass
class ManualBinary(BinaryDescriptor):
    content_type: str = "manual_binary"
    note: str = ""


@dataclass
class DocDescriptor(ContentDescriptor):
    content_type: str = "documentation"
    source: Optional[RegistrySource] = None
    doc_info: Optional[DocInfo] = None
    linked_content_id: str = ""


@dataclass
class RegistryDescriptor(ContentDescriptor):
    content_type: str = "registry"
    url: str = ""
    repo: GitHubRepo = field(default_factory=GitHubRepo)
    status: str = "pending"
    error_msg: str = ""
    selected_content: Optional[list] = None
    last_refresh: Optional[str] = None
