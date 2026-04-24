"""
pipeline_state.py — ContentSerializer (gzip .apf_cache) and InstallRecord.

No legacy fallbacks: old .apf_meta.json / cache_manifest.json are silently ignored.
"""
from __future__ import annotations

import dataclasses
import gzip
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, get_type_hints

from .content_base import ContentDescriptor, GitHubRepo

_CACHE_FILENAME = ".apf_cache"
CURRENT_SCHEMA_VERSION = 2

_TYPE_MAP: dict[str, type] = {}


def _get_type_map() -> dict[str, type]:
    if not _TYPE_MAP:
        from .content_types import (
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
    except Exception:
        hints = {}
    kwargs = {}
    for f in dataclasses.fields(cls):
        if f.name not in data:
            continue
        val = data[f.name]
        ft = hints.get(f.name)
        inner = None
        if hasattr(ft, "__args__"):
            inner = next((a for a in ft.__args__ if a is not type(None)), None)
        target_cls = (
            inner if inner and dataclasses.is_dataclass(inner)
            else (ft if ft and dataclasses.is_dataclass(ft) else None)
        )
        if target_cls and isinstance(val, dict):
            val = _from_dict_recursive(target_cls, val)
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

    def load_cache(self, cache_dir: Path) -> Optional[tuple[ContentDescriptor, str]]:
        path = cache_dir / _CACHE_FILENAME
        if not path.exists():
            return None
        try:
            with gzip.open(str(path), "rt", encoding="utf-8") as f:
                d = json.load(f)
            return self.from_dict(d["content"]), d.get("cached_at", "")
        except Exception:
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
    install_type: str = ""
    components: list = field(default_factory=list)
    bp_pak_files_deployed: list = field(default_factory=list)
    capabilities_includes: list = field(default_factory=list)
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
        from .content_base import RegistrySource
        from .content_types import (
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
        if isinstance(content, BinaryDescriptor):
            r.install_type = content.install_type
            if bp_pak_files_deployed:
                r.bp_pak_files_deployed = bp_pak_files_deployed
        return r
