"""
VersionManager — reads and writes the three component versions from source files.

Component → source file:
  Framework  CMakeLists.txt                      project(APFramework VERSION x.y.z)
  Manager    tools/apf_manager/__version__.py    __version__ = "x.y.z"
  Apworld    worlds/apf/archipelago.json         "world_version": "x.y.z"

_REPO_ROOT must be set at runtime via set_repo_root().
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Optional

_REPO_ROOT: Optional[Path] = None

_TAG_PREFIX = {
    "framework": "framework",
    "manager":   "manager",
    "apworld":   "apworld",
}


def set_repo_root(path: Optional[Path]) -> None:
    global _REPO_ROOT
    _REPO_ROOT = path


def is_repo_valid() -> bool:
    return _REPO_ROOT is not None and (_REPO_ROOT / ".git").is_dir()


def _build_file_map() -> dict:
    if _REPO_ROOT is None:
        return {}
    return {
        "framework": _REPO_ROOT / "CMakeLists.txt",
        "manager":   _REPO_ROOT / "tools" / "apf_manager" / "__version__.py",
        "apworld":   _REPO_ROOT / "worlds" / "apf" / "archipelago.json",
    }


def get_framework_version() -> Optional[str]:
    if not is_repo_valid():
        return None
    try:
        text = _build_file_map()["framework"].read_text(encoding="utf-8")
        m = re.search(r'project\s*\(\s*APFramework\s+VERSION\s+([\d.]+)', text)
        return m.group(1) if m else None
    except Exception:
        return None


def get_manager_version() -> Optional[str]:
    if not is_repo_valid():
        return None
    try:
        ns: dict = {}
        exec(_build_file_map()["manager"].read_text(encoding="utf-8"), ns)
        return ns.get("__version__")
    except Exception:
        return None


def get_apworld_version() -> Optional[str]:
    if not is_repo_valid():
        return None
    try:
        data = json.loads(_build_file_map()["apworld"].read_text(encoding="utf-8"))
        return data.get("world_version")
    except Exception:
        return None


def get_all_versions() -> dict[str, Optional[str]]:
    return {
        "framework": get_framework_version(),
        "manager":   get_manager_version(),
        "apworld":   get_apworld_version(),
    }


def bump_version(version: str, part: str) -> str:
    parts = (version or "0.0.0").split(".")
    while len(parts) < 3:
        parts.append("0")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def set_framework_version(version: str) -> bool:
    if not is_repo_valid():
        return False
    try:
        path = _build_file_map()["framework"]
        text = path.read_text(encoding="utf-8")
        new_text = re.sub(
            r'(project\s*\(\s*APFramework\s+VERSION\s+)[\d.]+',
            rf'\g<1>{version}',
            text,
        )
        path.write_text(new_text, encoding="utf-8")
        return True
    except Exception:
        return False


def set_manager_version(version: str) -> bool:
    if not is_repo_valid():
        return False
    try:
        path = _build_file_map()["manager"]
        text = path.read_text(encoding="utf-8")
        new_text = re.sub(
            r'(__version__\s*=\s*["\'])[\d.]+(["\'])',
            rf'\g<1>{version}\g<2>',
            text,
        )
        path.write_text(new_text, encoding="utf-8")
        return True
    except Exception:
        return False


def set_apworld_version(version: str) -> bool:
    if not is_repo_valid():
        return False
    try:
        path = _build_file_map()["apworld"]
        data = json.loads(path.read_text(encoding="utf-8"))
        data["world_version"] = version
        path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        return True
    except Exception:
        return False


_WRITERS = {
    "framework": set_framework_version,
    "manager":   set_manager_version,
    "apworld":   set_apworld_version,
}


def set_version(component: str, version: str) -> bool:
    writer = _WRITERS.get(component)
    return writer(version) if writer else False


def get_current_branch() -> Optional[str]:
    if not is_repo_valid():
        return None
    try:
        return subprocess.check_output(
            ["git", "branch", "--show-current"],
            text=True, cwd=str(_REPO_ROOT),
        ).strip() or None
    except Exception:
        return None


def commit_and_tag(component: str, version: str) -> tuple[bool, str]:
    if not is_repo_valid():
        return False, "Repo root not configured — see Dev Setup tab."
    fm = _build_file_map()
    file_path = str(fm.get(component, ""))
    if not file_path:
        return False, f"Unknown component: {component!r}"

    tag = f"{_TAG_PREFIX[component]}/v{version}"
    commit_msg = f"Bump {component} version to {version}"

    steps = [
        (["git", "add", file_path],           "stage"),
        (["git", "commit", "-m", commit_msg], "commit"),
        (["git", "push"],                     "push"),
        (["git", "tag", tag],                 "tag"),
        (["git", "push", "origin", tag],      "push tag"),
    ]
    for cmd, label in steps:
        try:
            subprocess.check_output(
                cmd, cwd=str(_REPO_ROOT), stderr=subprocess.STDOUT, text=True)
        except subprocess.CalledProcessError as exc:
            return False, f"git {label} failed:\n{exc.output}"

    return True, ""
