from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GitHubRepo:
    owner: str = ""
    repo: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}" if self.owner and self.repo else ""

    @classmethod
    def from_full_name(cls, full_name: str) -> "GitHubRepo":
        parts = full_name.split("/", 1)
        return cls(owner=parts[0], repo=parts[1]) if len(parts) == 2 else cls()


@dataclass
class ContentDescriptor:
    content_type: str = ""
    name: str = ""
    version: str = ""
    game_id: str = ""


@dataclass
class RegistrySource:
    repo: GitHubRepo = field(default_factory=GitHubRepo)
    registry_url: str = ""
    folder: str = ""
    submodule_parent: Optional[GitHubRepo] = None

    @property
    def source_package_id(self) -> str:
        return self.repo.full_name

    @property
    def is_submodule(self) -> bool:
        return self.submodule_parent is not None


@dataclass
class ReleaseSource:
    repo: GitHubRepo = field(default_factory=GitHubRepo)
    tag: str = ""
    published_at: str = ""
    changelog: str = ""
    is_prerelease: bool = False
    recommended_by: Optional[GitHubRepo] = None


@dataclass
class ManualSource:
    url: str = ""
    note: str = ""


@dataclass
class ModComponents:
    lua: bool = False
    cpp: bool = False
    blueprint: bool = False
    bp_pak_files: list = field(default_factory=list)
    # Per-subfolder BP metadata from the registry resolver.
    # Each entry: {"name": str, "files": list[str], "is_valid": bool, "warnings": list[str]}
    bp_subfolders: list = field(default_factory=list)

    @property
    def bp_mods(self) -> list:
        """Typed BpLogicMod instances from bp_subfolders (falls back to flat bp_pak_files)."""
        from .bp_component import parse_bp_mods
        if self.bp_subfolders:
            result = []
            for sf in self.bp_subfolders:
                if sf.get("is_valid") and sf.get("files"):
                    mods = parse_bp_mods(sf["files"])
                    if mods:
                        result.extend(mods)
            return result
        return parse_bp_mods(self.bp_pak_files) or []

    @property
    def component_count(self) -> int:
        return sum([self.lua, self.cpp, self.blueprint])

    @property
    def is_combined(self) -> bool:
        return self.component_count >= 2

    @property
    def is_standalone(self) -> bool:
        return self.component_count == 1

    @property
    def types(self) -> list[str]:
        return (["lua"] if self.lua else []) + \
               (["cpp"] if self.cpp else []) + \
               (["blueprint"] if self.blueprint else [])

    @classmethod
    def from_lists(
        cls,
        components: list[str],
        bp_pak_files: list[str],
        *,
        bp_subfolders: list | None = None,
    ) -> "ModComponents":
        return cls(
            lua="lua" in components,
            cpp="cpp" in components,
            blueprint="blueprint" in components,
            bp_pak_files=bp_pak_files,
            bp_subfolders=bp_subfolders or [],
        )


@dataclass
class DocInfo:
    docs_url: str = ""
    readme_url: str = ""
    doc_type: str = ""

    @property
    def has_docs(self) -> bool:
        return bool(self.docs_url or self.readme_url)


@dataclass
class DependencySpec:
    mod_id: str = ""
    version_constraint: str = ""
    is_incompatible: bool = False


@dataclass
class ContentAsset:
    name: str = ""
    url: str = ""
    size_bytes: int = 0
    selected: bool = False


@dataclass
class ContentTags:
    is_framework: bool = False
    is_cross_game: bool = False
    is_submodule: bool = False
    has_conflict: bool = False
    has_duplicate_source: bool = False
    content_hash: str = ""
    labels: list = field(default_factory=list)
