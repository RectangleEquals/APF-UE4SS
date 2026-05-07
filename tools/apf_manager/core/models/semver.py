"""
Semantic versioning utilities — shared across plugins.

Extracted from plugins/mods/capabilities_builder.py for use by
both the mods plugin and the updates plugin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[a-zA-Z0-9._-]+))?"
    r"(?:\+(?P<build>[a-zA-Z0-9._-]+))?$"
)


@dataclass
class SemVer:
    major: int
    minor: int
    patch: int
    pre: str = ""

    @classmethod
    def parse(cls, s: str) -> Optional["SemVer"]:
        m = _SEMVER_RE.match(s.strip())
        if not m:
            return None
        return cls(
            int(m.group("major")),
            int(m.group("minor")),
            int(m.group("patch")),
            m.group("pre") or "",
        )

    def _tuple(self):
        # Pre-release < release; empty pre-release = release version
        pre_key = (0, "") if not self.pre else (1, self.pre)
        return (self.major, self.minor, self.patch, pre_key)

    def __lt__(self, other):  return self._tuple() < other._tuple()
    def __le__(self, other):  return self._tuple() <= other._tuple()
    def __gt__(self, other):  return self._tuple() > other._tuple()
    def __ge__(self, other):  return self._tuple() >= other._tuple()
    def __eq__(self, other):  return self._tuple() == other._tuple()

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.pre}" if self.pre else base


# Keep the old private name as an alias for backward compatibility
_SemVer = SemVer
