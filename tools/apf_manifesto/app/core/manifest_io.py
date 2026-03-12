"""
core/manifest_io.py

Load, save, and create AP Framework manifest.json files.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .manifest_model import (
    ActionArg, Capabilities, Goal, ItemDef, ItemOverride,
    LocationDef, LocationOverride, ManifestModel, Overrides,
    RangeOption, RegionDef, TextChoiceOption, ToggleOption,
)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_manifest(path: str) -> ManifestModel:
    """Load a manifest.json and deserialise it into a ManifestModel."""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    m = ManifestModel()
    m._path = str(p)
    m._folder_name = p.parent.name

    m.mod_id           = raw.get("mod_id", "")
    m.name             = raw.get("name", "")
    m.version          = raw.get("version", "1.0.0")
    m.enabled          = raw.get("enabled", True)
    m.description      = raw.get("description", "")
    m.vocab_validation = raw.get("vocab_validation", False)
    m.depends          = raw.get("depends", [])
    m.incompatible     = raw.get("incompatible", [])
    m.options          = _load_options(raw.get("options", {}))
    m.goals            = _load_goals(raw.get("goals", []))
    m.capabilities     = _load_capabilities(raw.get("capabilities", {}))
    return m



def _load_options(raw: dict) -> dict:
    result = {}
    for key, val in raw.items():
        t = val.get("type", "toggle")
        if t == "toggle":
            result[key] = ToggleOption(
                default=val.get("default", False),
                description=val.get("description", ""),
            )
        elif t == "range":
            result[key] = RangeOption(
                range_start=val.get("range_start", 0),
                range_end=val.get("range_end", 10),
                default=val.get("default", 0),
                description=val.get("description", ""),
            )
        elif t == "text_choice":
            result[key] = TextChoiceOption(
                choices=val.get("choices", []),
                default=val.get("default", ""),
                description=val.get("description", ""),
            )
    return result


def _load_goals(raw: list) -> list[Goal]:
    return [
        Goal(
            name=g.get("name", ""),
            display=g.get("display", ""),
            description=g.get("description", ""),
            logic=g.get("logic", ""),
        )
        for g in raw
    ]


def _load_capabilities(raw: dict) -> Capabilities:
    cap = Capabilities()
    cap.include = raw.get("include", [])
    cap.regions = [
        RegionDef(name=r.get("name", ""), logic=r.get("logic", ""))
        for r in raw.get("regions", [])
    ]
    cap.items = [
        ItemDef(
            name=i.get("name", ""),
            type=i.get("type", "filler"),
            amount=i.get("amount", 1),
            logic=i.get("logic", ""),
            action=i.get("action"),
            args=[ActionArg(**a) for a in i.get("args", [])],
        )
        for i in raw.get("items", [])
    ]
    cap.locations = [
        LocationDef(
            name=lc.get("name", ""),
            logic=lc.get("logic", ""),
            amount=lc.get("amount", 1),
        )
        for lc in raw.get("locations", [])
    ]
    ov_raw = raw.get("overrides", {})
    cap.overrides = Overrides(
        items=[
            ItemOverride(
                target_item=o.get("target_item", ""),
                target_mod=o.get("target_mod", ""),
                type=o.get("type", "filler"),
                logic=o.get("logic", ""),
            )
            for o in ov_raw.get("items", [])
        ],
        locations=[
            LocationOverride(
                name=o.get("name", ""),
                target_mod=o.get("target_mod", ""),
                logic=o.get("logic", ""),
            )
            for o in ov_raw.get("locations", [])
        ],
    )
    return cap



# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_manifest(model: ManifestModel) -> None:
    """Serialise ManifestModel → manifest.json. Omits empty optional fields."""
    if not model._path:
        raise ValueError("ManifestModel has no _path — cannot save.")
    raw = _model_to_dict(model)
    Path(model._path).write_text(
        json.dumps(raw, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )


def _model_to_dict(m: ManifestModel) -> dict:
    d: dict[str, Any] = {}
    d["mod_id"]  = m.mod_id
    d["name"]    = m.name
    d["version"] = m.version
    d["enabled"] = m.enabled
    if m.description:
        d["description"] = m.description
    if m.vocab_validation:
        d["vocab_validation"] = True
    if m.depends:
        d["depends"] = m.depends
    if m.incompatible:
        d["incompatible"] = m.incompatible
    if m.options:
        d["options"] = _dump_options(m.options)
    if m.goals:
        d["goals"] = _dump_goals(m.goals)
    cap = _dump_capabilities(m.capabilities)
    if cap:
        d["capabilities"] = cap
    return d


def _dump_options(opts: dict) -> dict:
    result = {}
    for key, opt in opts.items():
        if isinstance(opt, ToggleOption):
            result[key] = {"type": "toggle", "default": opt.default,
                           "description": opt.description}
        elif isinstance(opt, RangeOption):
            result[key] = {"type": "range", "range_start": opt.range_start,
                           "range_end": opt.range_end, "default": opt.default,
                           "description": opt.description}
        elif isinstance(opt, TextChoiceOption):
            result[key] = {"type": "text_choice", "choices": opt.choices,
                           "default": opt.default, "description": opt.description}
    return result


def _dump_goals(goals: list[Goal]) -> list:
    return [
        {k: v for k, v in {
            "name": g.name, "display": g.display,
            "description": g.description, "logic": g.logic,
        }.items() if v}
        for g in goals
    ]



def _dump_capabilities(cap: Capabilities) -> dict:
    d: dict = {}
    if cap.include:
        d["include"] = cap.include
    if cap.regions:
        d["regions"] = [
            {k: v for k, v in {"name": r.name, "logic": r.logic}.items() if v}
            for r in cap.regions
        ]
    if cap.items:
        d["items"] = []
        for it in cap.items:
            entry: dict = {"name": it.name, "type": it.type, "amount": it.amount}
            if it.logic:
                entry["logic"] = it.logic
            if it.action:
                entry["action"] = it.action
                entry["args"]   = [{"name": a.name, "type": a.type,
                                     "value": a.value} for a in it.args]
            d["items"].append(entry)
    if cap.locations:
        d["locations"] = []
        for lc in cap.locations:
            entry = {"name": lc.name}
            if lc.logic:
                entry["logic"] = lc.logic
            if lc.amount != 1:
                entry["amount"] = lc.amount
            d["locations"].append(entry)
    ov = _dump_overrides(cap.overrides)
    if ov:
        d["overrides"] = ov
    return d


def _dump_overrides(ov: Overrides) -> dict:
    d: dict = {}
    if ov.items:
        d["items"] = [
            {k: v for k, v in {
                "target_item": o.target_item,
                "target_mod": o.target_mod,
                "type": o.type,
                "logic": o.logic,
            }.items() if v}
            for o in ov.items
        ]
    if ov.locations:
        d["locations"] = [
            {k: v for k, v in {
                "name": o.name,
                "target_mod": o.target_mod,
                "logic": o.logic,
            }.items() if v}
            for o in ov.locations
        ]
    return d


# ---------------------------------------------------------------------------
# Create new mod
# ---------------------------------------------------------------------------

def new_manifest(mods_dir: str, mod_name: str, mod_id: str = "") -> ManifestModel:
    """
    Scaffold a new mod directory with a blank manifest.json.
    Returns the unsaved ManifestModel (call save_manifest() after editing).
    """
    folder = Path(mods_dir) / mod_name
    folder.mkdir(parents=True, exist_ok=True)
    scripts = folder / "Scripts"
    scripts.mkdir(exist_ok=True)

    manifest_path = str(folder / "manifest.json")
    m = ManifestModel()
    m._path        = manifest_path
    m._folder_name = mod_name
    m.mod_id       = mod_id or f"author.game.{_slug(mod_name)}"
    m.name         = mod_name
    m.version      = "1.0.0"
    m.enabled      = True
    save_manifest(m)
    return m


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

