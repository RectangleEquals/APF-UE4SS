"""descriptor_factory.py — typed descriptor builders extracted from RegistryService (Fix D)."""
from __future__ import annotations

import hashlib
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from .resolver import DiscoveredMod


def _parse_manifest_deps(manifest: dict, log_fn: Optional[Callable] = None) -> list:
    """Convert manifest 'depends'/'incompatible' arrays to DependencySpec objects."""
    from ...models.descriptors.base import DependencySpec
    result = []
    for kind, is_incompat in [("depends", False), ("incompatible", True)]:
        for s in manifest.get(kind, []):
            try:
                parts = str(s).strip().split(" ", 1)
                result.append(DependencySpec(
                    mod_id=parts[0],
                    version_constraint=parts[1] if len(parts) > 1 else "",
                    is_incompatible=is_incompat,
                ))
            except Exception as exc:
                if log_fn:
                    log_fn(f"[registry] WARN: malformed dep entry '{s}': {exc}")
    return result


def to_content_descriptor(mod: "DiscoveredMod", entry, log_fn: Optional[Callable] = None):
    """Convert a DiscoveredMod to the appropriate typed ContentDescriptor subclass."""
    from ...models.descriptors.base import GitHubRepo, RegistrySource, ModComponents, DocInfo, ContentTags
    from ...models.descriptors.types import (
        APModDescriptor, FrameworkModDescriptor, ThirdPartyModDescriptor,
    )
    from .resolver import _is_framework_mod_id

    source = RegistrySource(
        repo=entry.repo,
        registry_url=entry.url,
        folder=mod.folder,
        submodule_parent=(
            GitHubRepo.from_full_name(mod.submodule_of)
            if getattr(mod, "submodule_of", None) else None
        ),
    )
    components = ModComponents.from_lists(
        mod.components or [], mod.bp_pak_files or [],
        bp_subfolders=getattr(mod, "bp_subfolders", []),
    )
    docs = DocInfo(readme_url=mod.readme_url or "")
    tags = ContentTags(
        is_framework=_is_framework_mod_id(mod.mod_id or ""),
        is_submodule=source.is_submodule,
    )
    name = mod.manifest.get("name") or mod.folder.split("/")[-1]
    version = mod.manifest.get("version", "")
    if mod.mod_id:
        parts = mod.mod_id.split(".")
        game_id = parts[1] if len(parts) >= 2 else ""
        parsed_deps = _parse_manifest_deps(mod.manifest, log_fn)
        if _is_framework_mod_id(mod.mod_id):
            return FrameworkModDescriptor(
                name=name, version=version, game_id=game_id,
                folder_name=mod.folder.split("/")[-1],
                description=mod.manifest.get("description", ""),
                author=mod.manifest.get("author", ""),
                mod_id=mod.mod_id,
                source=source, components=components, docs=docs, tags=tags,
                capabilities_includes=mod.manifest.get("capabilities", {}).get("include", []),
                dependencies=parsed_deps,
            )
        return APModDescriptor(
            name=name, version=version, game_id=game_id,
            folder_name=mod.folder.split("/")[-1],
            description=mod.manifest.get("description", ""),
            author=mod.manifest.get("author", ""),
            mod_id=mod.mod_id,
            source=source, components=components, docs=docs, tags=tags,
            capabilities_includes=mod.manifest.get("capabilities", {}).get("include", []),
            dependencies=parsed_deps,
        )
    return ThirdPartyModDescriptor(
        name=name, version=version,
        game_id=entry.game_id,
        folder_name=mod.folder.split("/")[-1],
        description=mod.manifest.get("description", ""),
        author=mod.manifest.get("author", ""),
        source=source, components=components, docs=docs, tags=tags,
    )


def to_template_descriptor(tpath: str, repos: list, entry):
    """Build a TemplateDescriptor from a template path, contributing repo list, and registry entry."""
    from ...models.descriptors.base import GitHubRepo, RegistrySource, ContentTags
    from ...models.descriptors.types import TemplateDescriptor
    first_repo = GitHubRepo.from_full_name(repos[0]) if repos else entry.repo
    conflict_sources = [GitHubRepo.from_full_name(r) for r in repos[1:]]
    game_dir = tpath.split("/")[-1] if "/" in tpath else tpath
    return TemplateDescriptor(
        name=game_dir,
        game_id=game_dir,
        template_path=tpath,
        source=RegistrySource(repo=first_repo, registry_url=entry.url, folder=tpath),
        tags=ContentTags(has_conflict=len(repos) > 1),
        conflict_sources=conflict_sources,
    )


def to_binary_descriptor(opt: dict, entry):
    """Build a typed BinaryDescriptor from a ue4ss.json option dict and its registry entry."""
    from ...models.descriptors.base import GitHubRepo, RegistrySource, DocInfo, ContentTags
    from ...models.descriptors.types import (
        GithubReleaseBinary, ExternalUrlBinary, ManualBinary, ReleaseSource,
    )

    otype = opt.get("type", "manual")
    raw_repo = opt.get("repo", "")
    tag = opt.get("tag", "")
    owner, repo_name = raw_repo.split("/", 1) if "/" in raw_repo else ("", raw_repo)
    name = opt.get("note", "UE4SS")
    install_type = opt.get("install_type", "ue4ss")

    # K-11 Fix A: parse the optional 'docs' field (registry-relative path → full raw URL).
    docs_path = opt.get("docs", "")
    docs = None
    if docs_path:
        raw_doc_url = (
            f"https://raw.githubusercontent.com/"
            f"{entry.repo.owner}/{entry.repo.repo}/HEAD/{docs_path}"
        )
        docs = DocInfo(readme_url=raw_doc_url)

    if otype == "github_release":
        fp = "|".join([owner, repo_name, tag, install_type, entry.repo.full_name, "github_release"])
        content_hash = hashlib.sha256(fp.encode()).hexdigest()[:20]
        return GithubReleaseBinary(
            name=name,
            install_type=install_type,
            source=ReleaseSource(
                repo=GitHubRepo(owner=owner, repo=repo_name),
                tag=tag,
                is_prerelease=opt.get("prerelease", False),
            ),
            registry_source=RegistrySource(repo=entry.repo, registry_url=entry.url, folder=""),
            tags=ContentTags(content_hash=content_hash),
            docs=docs,
        )
    elif otype == "external_url":
        return ExternalUrlBinary(
            name=name, install_type=install_type,
            url=opt.get("url", ""), note=name, docs=docs,
        )
    else:
        return ManualBinary(name=name, install_type=install_type, note=name, docs=docs)
