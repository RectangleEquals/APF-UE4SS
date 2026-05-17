"""
pipeline.py — ContentSerializer (gzip .apf_cache) and InstallRecord.

No legacy fallbacks: old .apf_meta.json / cache_manifest.json are silently ignored.
"""
from __future__ import annotations

import dataclasses
import gzip
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union, get_type_hints, get_origin, get_args

from ..descriptors.base import ContentDescriptor, GitHubRepo

_CACHE_FILENAME = ".apf_cache"
CURRENT_SCHEMA_VERSION = 2

_TYPE_MAP: dict[str, type] = {}


def _get_type_map() -> dict[str, type]:
    if not _TYPE_MAP:
        from ..descriptors.types import (
            ThirdPartyModDescriptor, APModDescriptor, FrameworkModDescriptor,
            TemplateDescriptor, GithubReleaseBinary, ExternalUrlBinary,
            ManualBinary, DocDescriptor, RegistryDescriptor,
        )
        _TYPE_MAP.update({
            "third_party_mod": ThirdPartyModDescriptor,
            "ap_mod": APModDescriptor,
            "framework_mod": FrameworkModDescriptor,
            "template": TemplateDescriptor,
            "github_release_binary": GithubReleaseBinary,
            "external_url_binary": ExternalUrlBinary,
            "manual_binary": ManualBinary,
            "documentation": DocDescriptor,
            "registry": RegistryDescriptor,
        })
    return _TYPE_MAP


def _from_dict_recursive(cls, data: dict):
    if not dataclasses.is_dataclass(cls) or not isinstance(data, dict):
        return data
    try:
        hints = get_type_hints(cls)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("[pipeline] WARN: get_type_hints failed for %s: %s", cls, exc)
        hints = {}
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        val = data[f.name]
        ft = hints.get(f.name)

        # Unwrap Optional[X] → X using the documented typing API.
        # Optional[X] is Union[X, None]; get_origin returns Union, get_args returns (X, NoneType).
        effective = ft
        if get_origin(ft) is Union:
            non_none = [a for a in get_args(ft) if a is not type(None)]
            if len(non_none) == 1:
                effective = non_none[0]

        # Path A: effective is list[DataClass] — handles list[DC] and Optional[list[DC]]
        list_item_cls = None
        if get_origin(effective) is list:
            args = get_args(effective)
            if args and dataclasses.is_dataclass(args[0]):
                list_item_cls = args[0]

        # Path B: effective is a direct dataclass (no generic wrapper)
        direct_cls = effective if (effective is not None and dataclasses.is_dataclass(effective)) else None

        if list_item_cls and isinstance(val, list):
            val = [
                _from_dict_recursive(list_item_cls, item) if isinstance(item, dict) else item
                for item in val
            ]
        elif direct_cls and isinstance(val, dict):
            val = _from_dict_recursive(direct_cls, val)
        kwargs[f.name] = val
    return cls(**kwargs)


class ContentSerializer:
    def to_dict(self, content: ContentDescriptor) -> dict:
        return dataclasses.asdict(content)

    def from_dict(self, d: dict) -> ContentDescriptor:
        ct = d.get("content_type", "")
        cls = _get_type_map().get(ct, ContentDescriptor)
        return _from_dict_recursive(cls, d)

    def save_cache(self, cache_dir: Path, content: ContentDescriptor) -> None:
        payload = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "content": self.to_dict(content),
        }
        cache_dir.mkdir(parents=True, exist_ok=True)
        with gzip.open(str(cache_dir / _CACHE_FILENAME), "wt", encoding="utf-8", compresslevel=6) as f:
            json.dump(payload, f, separators=(",", ":"), default=str)

    def load_cache(
        self, cache_dir: Path, log_fn=None
    ) -> Optional[tuple[ContentDescriptor, str]]:
        path = cache_dir / _CACHE_FILENAME
        if not path.exists():
            return None
        try:
            with gzip.open(str(path), "rt", encoding="utf-8") as f:
                d = json.load(f)
            return self.from_dict(d["content"]), d.get("cached_at", "")
        except Exception as exc:
            if log_fn:
                log_fn(f"[cache] WARN: failed to load {path}: {exc}")
            return None


@dataclass
class InstallRecord:
    content_type: str = ""
    name: str = ""
    version: str = ""
    game_id: str = ""
    folder_name: str = ""
    description: str = ""
    author: str = ""
    mod_id: str = ""
    source_registry_url: str = ""
    source_repo: str = ""
    source_folder: str = ""
    source_tag: str = ""   # GitHub release tag captured at install time (Fallback B for version display)
    install_type: str = ""
    components: list = field(default_factory=list)
    bp_pak_files_deployed: list = field(default_factory=list)
    binary_files_deployed: list = field(default_factory=list)  # top-level names in platform_dir written at install time
    capabilities_includes: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)  # list[str] mod_ids this mod hard-depends on
    deployed_at: str = ""

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        return {k: v for k, v in d.items() if v not in (None, "", [], {})}

    @classmethod
    def from_dict(cls, d: dict) -> "InstallRecord":
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})

    @classmethod
    def from_content(
        cls,
        content: ContentDescriptor,
        game_id: str,
        bp_pak_files_deployed: Optional[list] = None,
    ) -> "InstallRecord":
        from ..descriptors.base import RegistrySource, DependencySpec
        from ..descriptors.types import (
            ModDescriptor, APModDescriptor, BinaryDescriptor, RegistryDescriptor,
        )
        r = cls(
            content_type=content.content_type,
            name=content.name,
            version=content.version,
            game_id=game_id,
            deployed_at=datetime.now(timezone.utc).isoformat(),
        )
        if isinstance(content, ModDescriptor):
            r.folder_name = content.folder_name
            r.description = content.description
            r.author = content.author
            if content.source:
                r.source_registry_url = content.source.registry_url
                r.source_repo = content.source.repo.full_name
                r.source_folder = content.source.folder
            if content.components:
                r.components = content.components.types
                r.bp_pak_files_deployed = bp_pak_files_deployed or content.components.bp_pak_files
        if isinstance(content, APModDescriptor):
            r.mod_id = content.mod_id
            r.capabilities_includes = list(content.capabilities_includes)
            r.dependencies = [
                d.mod_id for d in (content.dependencies or [])
                if isinstance(d, DependencySpec) and not d.is_incompatible and d.mod_id
            ]
        if isinstance(content, BinaryDescriptor):
            r.install_type = content.install_type
            if bp_pak_files_deployed:
                r.bp_pak_files_deployed = bp_pak_files_deployed
            src = getattr(content, "source", None)
            if src:
                r.source_tag = getattr(src, "tag", "") or ""
        return r
