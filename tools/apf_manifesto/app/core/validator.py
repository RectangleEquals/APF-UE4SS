"""
core/validator.py

Validates a ManifestModel against the APF schema rules (manifest.md, logic.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .logic_parser import parse, validate_scope
from .manifest_model import ManifestModel, TextChoiceOption, RangeOption
from .mod_registry import ModRegistry


@dataclass
class ValidationError:
    severity: Literal["error", "warning"]
    path: str       # dotted path into manifest, e.g. "capabilities.items[2].logic"
    message: str


_MOD_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+$")


class ManifestValidator:
    def __init__(self, registry: ModRegistry | None = None):
        self._registry = registry

    def validate(self, model: ManifestModel) -> list[ValidationError]:
        errors: list[ValidationError] = []
        self._check_mod_id(model, errors)
        self._check_options(model, errors)
        self._check_goals_logic(model, errors)
        self._check_capabilities(model, errors)
        if self._registry:
            self._check_deps(model, errors)
            self._check_conflicts(model, errors)
            self._check_priority_mod(model, errors)
        return errors

    # ------------------------------------------------------------------

    def _add(self, errors, severity, path, msg):
        errors.append(ValidationError(severity=severity, path=path, message=msg))

    def _check_mod_id(self, m: ManifestModel, errors):
        if not m.mod_id:
            self._add(errors, "error", "mod_id", "mod_id is required.")
        elif not _MOD_ID_RE.match(m.mod_id):
            self._add(errors, "error", "mod_id",
                      f"mod_id '{m.mod_id}' must follow 'author.game.modname' format.")

    def _check_options(self, m: ManifestModel, errors):
        for key, opt in m.options.items():
            path = f"options.{key}"
            if isinstance(opt, TextChoiceOption):
                if not opt.choices:
                    self._add(errors, "error", path, "text_choice requires at least one choice.")
                elif opt.default not in opt.choices:
                    self._add(errors, "error", path,
                              f"default '{opt.default}' is not in choices {opt.choices}.")
            elif isinstance(opt, RangeOption):
                try:
                    dv = int(opt.default)
                    if not (opt.range_start <= dv <= opt.range_end):
                        self._add(errors, "error", path,
                                  f"default {dv} is outside range "
                                  f"[{opt.range_start}, {opt.range_end}].")
                except (TypeError, ValueError):
                    self._add(errors, "warning", path,
                              f"default '{opt.default}' cannot be interpreted as int.")

    def _check_goals_logic(self, m: ManifestModel, errors):
        for i, g in enumerate(m.goals):
            path = f"goals[{i}].logic"
            self._parse_logic(g.logic, path, "region", errors)

    def _check_capabilities(self, m: ManifestModel, errors):
        cap = m.capabilities
        for i, r in enumerate(cap.regions):
            self._parse_logic(r.logic, f"capabilities.regions[{i}].logic",
                              "region", errors)
        for i, it in enumerate(cap.items):
            self._parse_logic(it.logic, f"capabilities.items[{i}].logic",
                              "item", errors)
        for i, lc in enumerate(cap.locations):
            self._parse_logic(lc.logic, f"capabilities.locations[{i}].logic",
                              "location", errors)
        for i, ov in enumerate(cap.overrides.items):
            self._parse_logic(ov.logic, f"capabilities.overrides.items[{i}].logic",
                              "item_override", errors)
        for i, ov in enumerate(cap.overrides.locations):
            self._parse_logic(ov.logic, f"capabilities.overrides.locations[{i}].logic",
                              "location", errors)

    def _parse_logic(self, logic_str, path, entry_type, errors):
        if not logic_str:
            return
        try:
            node = parse(logic_str)
            scope_errors = validate_scope(node, entry_type)
            for se in scope_errors:
                self._add(errors, "error", path, se)
        except ValueError as exc:
            self._add(errors, "error", path, f"Logic parse error: {exc}")

    def _check_deps(self, m: ManifestModel, errors):
        missing = self._registry.check_dependencies(m)
        for dep_id in missing:
            self._add(errors, "error", "depends",
                      f"Dependency '{dep_id}' is not present in the Mods folder.")

    def _check_conflicts(self, m: ManifestModel, errors):
        conflicts = self._registry.check_conflicts(m)
        for cid in conflicts:
            self._add(errors, "error", "incompatible",
                      f"Conflicting mod '{cid}' is active.")

    def _check_priority_mod(self, m: ManifestModel, errors):
        is_priority = m.mod_id.startswith("archipelago.")
        cap = m.capabilities
        has_caps = bool(cap.regions or cap.items or cap.locations)
        if is_priority and has_caps:
            self._add(errors, "error", "capabilities",
                      "Priority mods (archipelago.*) must not declare capabilities.")
