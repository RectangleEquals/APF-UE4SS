"""Diagnostics-local result dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DiagValidationItem:
    label: str
    detail: str
    status: str     # "ok" | "warn" | "error"


@dataclass
class PackageResult:
    out_path: Path
    included: list[str] = field(default_factory=list)
