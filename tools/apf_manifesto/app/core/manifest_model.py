"""
core/manifest_model.py
Pure-Python dataclasses mirroring the full APF manifest.json schema.
No Kivy dependency — safe to import from any context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

@dataclass
class ToggleOption:
    type: Literal["toggle"] = "toggle"
    default: bool = False
    description: str = ""


@dataclass
class RangeOption:
    type: Literal["range"] = "range"
    range_start: int = 0
    range_end: int = 10
    default: Union[int, str] = 0
    description: str = ""


@dataclass
class TextChoiceOption:
    type: Literal["text_choice"] = "text_choice"
    choices: list[str] = field(default_factory=list)
    default: str = ""
    description: str = ""


OptionDef = Union[ToggleOption, RangeOption, TextChoiceOption]



# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------

@dataclass
class Goal:
    name: str = ""
    display: str = ""
    description: str = ""
    logic: str = ""


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

@dataclass
class ActionArg:
    name: str = ""
    type: str = "string"   # "string" | "number" | "boolean" | "property"
    value: Any = None


@dataclass
class ItemDef:
    name: str = ""
    type: str = "filler"   # progression | useful | filler | trap
    amount: int = 1
    logic: str = ""
    action: Optional[str] = None
    args: list[ActionArg] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

@dataclass
class LocationDef:
    name: str = ""
    logic: str = ""
    amount: int = 1


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

@dataclass
class RegionDef:
    name: str = ""
    logic: str = ""



# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------

@dataclass
class ItemOverride:
    target_item: str = ""
    target_mod: str = ""
    type: str = "filler"
    logic: str = ""


@dataclass
class LocationOverride:
    name: str = ""
    target_mod: str = ""
    logic: str = ""


@dataclass
class Overrides:
    items: list[ItemOverride] = field(default_factory=list)
    locations: list[LocationOverride] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

@dataclass
class Capabilities:
    include: list[str] = field(default_factory=list)
    regions: list[RegionDef] = field(default_factory=list)
    items: list[ItemDef] = field(default_factory=list)
    locations: list[LocationDef] = field(default_factory=list)
    overrides: Overrides = field(default_factory=Overrides)


# ---------------------------------------------------------------------------
# Root manifest
# ---------------------------------------------------------------------------

@dataclass
class ManifestModel:
    mod_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    description: str = ""
    vocab_validation: bool = False
    depends: list[str] = field(default_factory=list)
    incompatible: list[str] = field(default_factory=list)
    options: dict[str, OptionDef] = field(default_factory=dict)
    goals: list[Goal] = field(default_factory=list)
    capabilities: Capabilities = field(default_factory=Capabilities)

    # Runtime-only — not serialised
    _path: Optional[str] = field(default=None, compare=False, repr=False)
    _folder_name: Optional[str] = field(default=None, compare=False, repr=False)
    _read_only: bool = field(default=False, compare=False, repr=False)

