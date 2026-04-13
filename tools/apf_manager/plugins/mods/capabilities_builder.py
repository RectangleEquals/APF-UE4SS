"""
CapabilitiesBuilder — Python equivalent of the C++ APModRegistry + APCapabilities assembly.

Standalone — no Kivy, no plugin host dependency. Importable directly by CI:
    import sys; sys.path.insert(0, "tools/apf_manager")
    from plugins.mods.capabilities_builder import CapabilitiesBuilder

In-app: ModService.build_capabilities() is the convenience wrapper.
RegistryService passes templates_dirs for remote manifests.

Replicates all of APModRegistry + APCapabilities:
  1. Include resolution  — mirrors APModRegistry::resolve_includes()
  2. Dependency resolution — topological sort, semver-aware
  3. Conflict detection   — incompatible field
  4. Vocabulary validation — when vocab_validation: true (warnings, not errors)
  5. ID assignment        — sequential integers matching C++ auto-increment
  6. Output format        — flat dict matching _process_capabilities() expectations
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .mod_service import ModInfo


# ---------------------------------------------------------------------------
# Semver helpers — imported from core/semver.py
# ---------------------------------------------------------------------------

from ...core.semver import _SemVer

_DEP_RE = re.compile(
    r"^(?P<mod_id>\S+?)(?:\s+\((?P<op>>=|<=|>|<|==|!=|~=)\s*(?P<ver>[^\)]+)\))?$"
)


def _parse_dep_string(dep: str) -> tuple[str, Optional[str], Optional[str]]:
    """Parse 'mod_id (>=1.0.0)' → (mod_id, op, version_str).  op/ver may be None."""
    m = _DEP_RE.match(dep.strip())
    if not m:
        return dep.strip(), None, None
    return m.group("mod_id"), m.group("op"), m.group("ver")


def _check_version_constraint(installed: str, op: str, required: str) -> bool:
    a = _SemVer.parse(installed)
    b = _SemVer.parse(required)
    if a is None or b is None:
        return True   # can't validate — pass through
    return {
        ">=": a >= b,
        "<=": a <= b,
        ">":  a > b,
        "<":  a < b,
        "==": a == b,
        "!=": a != b,
        "~=": a >= b and a.major == b.major,
    }.get(op, True)


# ---------------------------------------------------------------------------
# Build-time manifest representation (internal)
# ---------------------------------------------------------------------------

@dataclass
class _ManifestData:
    """Flattened view of a manifest after include resolution."""
    mod_id: str
    name: str
    version: str
    depends: list[str]
    incompatible: list[str]
    vocab_validation: bool
    items: list[dict]
    locations: list[dict]
    goals: list[dict]
    options: list[dict]
    item_overrides: list[dict]
    source_path: Optional[Path] = None   # for error messages


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

class CapabilitiesBuilder:
    """
    Assembles a capabilities dict from one or more mod manifests.

    All logic lives here — gen_capabilities.py is just a thin CLI wrapper.

    Usage (CI):
        builder = CapabilitiesBuilder()
        caps = builder.from_manifest_path(Path("manifest.json"), templates_dirs=[Path("Templates/Palworld")])
        capabilities_data = CapabilitiesBuilder.to_capabilities_data(caps)

    Usage (in-app, via ModService.build_capabilities()):
        caps = CapabilitiesBuilder().from_mod_infos(mod_infos, templates_dirs=[game_templates_dir])
    """

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def from_manifest_path(
        self,
        *paths: Path,
        game: str = "APFramework",
        templates_dirs: Optional[list[Path]] = None,
        strict: bool = False,
    ) -> dict:
        """
        Build capabilities from one or more manifest.json file paths.

        templates_dirs: directories searched (in order) when resolving capabilities.include paths.
        strict: if True, missing required dependencies are errors (default: warnings).
        """
        manifests: list[_ManifestData] = []
        for path in paths:
            raw = json.loads(path.read_text(encoding="utf-8"))
            resolved = self._resolve_includes(raw, path.parent, templates_dirs or [])
            manifests.append(self._raw_to_manifest_data(resolved, path))
        return self._assemble(manifests, game=game, strict=strict)

    def from_mod_infos(
        self,
        mods: list["ModInfo"],
        game: str = "APFramework",
        templates_dirs: Optional[list[Path]] = None,
        strict: bool = False,
    ) -> dict:
        """
        Build aggregated capabilities from parsed ModInfo objects.
        Used by ModService.build_capabilities() (installed mods) and DevTools fixture export.
        """
        manifests: list[_ManifestData] = []
        for mod in mods:
            if not mod.is_ap_mod:
                continue
            raw = self._mod_info_to_raw(mod)
            resolved = self._resolve_includes(raw, mod.folder_path, templates_dirs or [])
            manifests.append(self._raw_to_manifest_data(resolved, mod.folder_path / "manifest.json"))
        return self._assemble(manifests, game=game, strict=strict)

    @staticmethod
    def to_capabilities_data(caps: dict) -> str:
        """Base64-encode a capabilities dict → capabilities_data YAML value."""
        return base64.b64encode(json.dumps(caps).encode("utf-8")).decode("ascii")

    # ------------------------------------------------------------------
    # Include resolution (mirrors APModRegistry::resolve_includes)
    # ------------------------------------------------------------------

    def _resolve_includes(
        self,
        manifest_raw: dict,
        manifest_dir: Path,
        templates_dirs: list[Path],
        _visited: Optional[set] = None,
        _depth: int = 0,
    ) -> dict:
        """
        Recursively merge capabilities.include fragment files into manifest_raw.

        Fragment files (logic/*.json) contain partial capabilities dicts:
          {"regions": [...], "items": [...], "locations": [...]}
        Included content is PREPENDED to the manifest's own arrays (C++ behavior).

        templates_dirs should contain game-level dirs (e.g. Templates/Palworld/).
        Include paths are resolved relative to the logic/ subdirectory of each,
        mirroring ap_mod_registry.cpp::resolve_includes() which uses:
          shared_logic_dir = framework_folder / Templates / game_name / logic
        """
        if _visited is None:
            _visited = set()
        if _depth > 16:
            raise ValueError("capabilities.include recursion depth exceeded (cycle?)")

        caps = manifest_raw.get("capabilities", {})
        include_paths: list[str] = caps.get("include", [])
        if not include_paths:
            return manifest_raw

        # Search order (mirrors C++ two-tier resolution):
        #   1. manifest_dir (local mod folder)
        #   2. <templates_game_dir>/logic/ (shared framework templates)
        search_dirs = [manifest_dir] + [td / "logic" for td in templates_dirs]

        merged_items: list[dict] = []
        merged_locations: list[dict] = []
        merged_goals: list[dict] = []

        for inc_path_str in include_paths:
            resolved = self._find_include(inc_path_str, search_dirs)
            if resolved is None:
                raise FileNotFoundError(
                    f"capabilities.include '{inc_path_str}' not found in: "
                    + ", ".join(str(d) for d in search_dirs)
                )
            canon = str(resolved.resolve())
            if canon in _visited:
                continue  # cycle — skip (already merged)
            _visited.add(canon)

            frag_raw = json.loads(resolved.read_text(encoding="utf-8"))
            # Recurse for transitive includes
            frag_resolved = self._resolve_includes(
                {"capabilities": frag_raw},
                resolved.parent,
                templates_dirs,
                _visited,
                _depth + 1,
            )
            frag_caps = frag_resolved.get("capabilities", frag_raw)
            merged_items.extend(frag_caps.get("items", []))
            merged_locations.extend(frag_caps.get("locations", []))
            merged_goals.extend(frag_caps.get("goals", []))

        # Prepend included content before own content
        result = dict(manifest_raw)
        new_caps = dict(caps)
        new_caps["items"]     = merged_items     + caps.get("items", [])
        new_caps["locations"] = merged_locations + caps.get("locations", [])
        new_caps["goals"]     = merged_goals     + caps.get("goals", [])
        result["capabilities"] = new_caps
        return result

    @staticmethod
    def _find_include(inc_path_str: str, search_dirs: list[Path]) -> Optional[Path]:
        """Try each search directory in order; return first match."""
        for d in search_dirs:
            candidate = (d / inc_path_str).resolve()
            if candidate.exists():
                return candidate
        return None

    # ------------------------------------------------------------------
    # Dependency resolution (topological sort, semver-aware)
    # ------------------------------------------------------------------

    def _resolve_order(
        self,
        manifests: list[_ManifestData],
        strict: bool = False,
    ) -> list[_ManifestData]:
        """
        Topological sort of manifests by their depends[] field.
        Returns ordered list (dependencies before dependents).
        Raises on circular dependencies.
        Warns (or raises if strict=True) on missing required dependencies.
        """
        by_id: dict[str, _ManifestData] = {m.mod_id: m for m in manifests}

        warnings: list[str] = []

        # Validate constraints and collect edges
        edges: dict[str, list[str]] = {m.mod_id: [] for m in manifests}
        for m in manifests:
            for dep_str in m.depends:
                dep_id, op, ver = _parse_dep_string(dep_str)
                if dep_id not in by_id:
                    msg = f"Mod '{m.mod_id}' depends on '{dep_id}' which is not present"
                    if strict:
                        raise ValueError(msg)
                    warnings.append(msg)
                    continue
                if op and ver:
                    installed_ver = by_id[dep_id].version
                    if not _check_version_constraint(installed_ver, op, ver):
                        msg = (
                            f"Mod '{m.mod_id}' requires '{dep_id} ({op}{ver})' "
                            f"but installed version is '{installed_ver}'"
                        )
                        if strict:
                            raise ValueError(msg)
                        warnings.append(msg)
                edges[m.mod_id].append(dep_id)

        for w in warnings:
            import warnings as _w
            _w.warn(w, stacklevel=4)

        # Kahn's algorithm
        in_degree: dict[str, int] = {mid: 0 for mid in by_id}
        for mid, deps in edges.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[mid] += 1

        queue = [mid for mid, deg in in_degree.items() if deg == 0]
        queue.sort()  # stable ordering for mods with no deps
        order: list[str] = []
        while queue:
            cur = queue.pop(0)
            order.append(cur)
            for mid, deps in edges.items():
                if cur in deps:
                    in_degree[mid] -= 1
                    if in_degree[mid] == 0:
                        queue.append(mid)
                        queue.sort()

        if len(order) != len(by_id):
            cycle_ids = set(by_id) - set(order)
            raise ValueError(f"Circular dependency detected among mods: {', '.join(sorted(cycle_ids))}")

        return [by_id[mid] for mid in order if mid in by_id]

    # ------------------------------------------------------------------
    # Conflict detection
    # ------------------------------------------------------------------

    @staticmethod
    def _check_conflicts(manifests: list[_ManifestData]) -> None:
        """Raise if any two mods in the set are mutually incompatible."""
        mod_ids = {m.mod_id for m in manifests}
        for m in manifests:
            for inc_str in m.incompatible:
                dep_id, op, ver = _parse_dep_string(inc_str)
                if dep_id in mod_ids:
                    other = next(x for x in manifests if x.mod_id == dep_id)
                    conflict = True
                    if op and ver:
                        conflict = _check_version_constraint(other.version, op, ver)
                    if conflict:
                        raise ValueError(
                            f"Mod '{m.mod_id}' is incompatible with '{dep_id}' "
                            f"(version '{other.version}')"
                        )

    # ------------------------------------------------------------------
    # Vocabulary validation (mirrors APVocabulary::validate_manifest)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_vocabulary(
        m: _ManifestData,
        templates_dirs: list[Path],
    ) -> list[str]:
        """
        Validate item/location names against Templates/<GameName>/{Items,Locations}.json.
        templates_dirs should contain game-level dirs (e.g. Templates/Palworld/) so that
        vocab files are found at td / "Items.json" — mirrors ap_vocabulary.cpp behavior.
        Returns list of warning strings. Never raises (matching C++ behavior).
        """
        if not m.vocab_validation:
            return []

        warnings: list[str] = []

        def load_vocab(filename: str) -> Optional[set[str]]:
            for td in templates_dirs:
                p = td / filename
                if p.exists():
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(data, list):
                            return set(data)
                        if isinstance(data, dict):
                            return set(data.keys())
                    except Exception:
                        pass
            return None

        def fuzzy_suggest(name: str, vocab: set[str], limit: int = 3) -> list[str]:
            """Levenshtein-based suggestions."""
            def _lev(a, b):
                if len(a) < len(b):
                    a, b = b, a
                if not b:
                    return len(a)
                prev = list(range(len(b) + 1))
                for i, ca in enumerate(a):
                    curr = [i + 1]
                    for j, cb in enumerate(b):
                        curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
                    prev = curr
                return prev[-1]
            scored = [(v, _lev(name.lower(), v.lower())) for v in vocab]
            scored.sort(key=lambda x: x[1])
            return [v for v, _ in scored[:limit] if _ <= max(3, len(name) // 3)]

        item_vocab    = load_vocab("Items.json")
        loc_vocab     = load_vocab("Locations.json")

        if item_vocab:
            for it in m.items:
                n = it.get("name", "")
                if n and n not in item_vocab:
                    sugg = fuzzy_suggest(n, item_vocab)
                    msg = f"[vocab] Mod '{m.mod_id}': item '{n}' not in vocabulary"
                    if sugg:
                        msg += f" — did you mean: {', '.join(sugg)}?"
                    warnings.append(msg)

        if loc_vocab:
            for loc in m.locations:
                n = loc.get("name", "")
                if n and n not in loc_vocab:
                    sugg = fuzzy_suggest(n, loc_vocab)
                    msg = f"[vocab] Mod '{m.mod_id}': location '{n}' not in vocabulary"
                    if sugg:
                        msg += f" — did you mean: {', '.join(sugg)}?"
                    warnings.append(msg)

        return warnings

    # ------------------------------------------------------------------
    # ID assignment
    # ------------------------------------------------------------------

    @staticmethod
    def _build_canonical_ids(
        ordered: list[_ManifestData],
    ) -> tuple[dict[str, int], dict[str, int]]:
        """
        Assign sequential integer IDs (starting at 1) to items and locations.
        Matches C++ auto-increment: items first across all mods (dep order,
        definition order within each mod), then locations same.

        Returns (item_name_to_id, location_name_to_id).
        Handles name collisions: first occurrence wins; subsequent occurrences
        of same name reuse the same ID (cross-mod sharing).
        """
        item_ids: dict[str, int] = {}
        loc_ids: dict[str, int] = {}
        next_item_id = 1
        next_loc_id = 1

        for m in ordered:
            for it in m.items:
                name = it.get("name", "")
                if name and name not in item_ids:
                    item_ids[name] = next_item_id
                    next_item_id += 1

        for m in ordered:
            for loc in m.locations:
                name = loc.get("name", "")
                if name and name not in loc_ids:
                    loc_ids[name] = next_loc_id
                    next_loc_id += 1

        return item_ids, loc_ids

    # ------------------------------------------------------------------
    # Output assembly
    # ------------------------------------------------------------------

    def _assemble(
        self,
        manifests: list[_ManifestData],
        game: str = "APFramework",
        strict: bool = False,
        templates_dirs: Optional[list[Path]] = None,
    ) -> dict:
        """
        Run the full assembly pipeline and return a capabilities dict
        matching what worlds/apf/__init__.py._process_capabilities() expects.
        """
        if not manifests:
            raise ValueError("No AP mod manifests provided to CapabilitiesBuilder")

        # 1. Dependency ordering
        ordered = self._resolve_order(manifests, strict=strict)

        # 2. Conflict detection
        self._check_conflicts(ordered)

        # 3. Vocabulary validation (warnings only)
        vocab_warnings: list[str] = []
        if templates_dirs:
            for m in ordered:
                vocab_warnings.extend(self._validate_vocabulary(m, templates_dirs))
        if vocab_warnings:
            import warnings as _w
            for w in vocab_warnings:
                _w.warn(w, stacklevel=3)

        # 4. ID assignment
        item_ids, loc_ids = self._build_canonical_ids(ordered)

        # 5. Build aggregated lists
        all_items: list[dict] = []
        seen_items: set[str] = set()
        for m in ordered:
            for it in m.items:
                name = it.get("name", "")
                if not name or name in seen_items:
                    continue
                seen_items.add(name)
                entry = dict(it)
                entry["id"] = item_ids[name]
                all_items.append(entry)

        all_locations: list[dict] = []
        seen_locs: set[str] = set()
        for m in ordered:
            for loc in m.locations:
                name = loc.get("name", "")
                if not name or name in seen_locs:
                    continue
                seen_locs.add(name)
                entry = dict(loc)
                entry["id"] = loc_ids[name]
                all_locations.append(entry)

        # Goals: same-named goals across mods get their logic OR-merged.
        # Mirrors ap_capabilities.cpp which combines: "(mod1_logic) or (mod2_logic)".
        # All other fields (display_name, description, condition) come from first occurrence.
        goals_by_name: dict[str, dict] = {}
        for m in ordered:
            for g in m.goals:
                name = g.get("name", "")
                if not name:
                    continue
                if name not in goals_by_name:
                    goals_by_name[name] = dict(g)
                else:
                    existing = goals_by_name[name].get("logic", "")
                    new_logic = g.get("logic", "")
                    if existing and new_logic and existing != new_logic:
                        goals_by_name[name]["logic"] = f"({existing}) or ({new_logic})"
                    elif new_logic and not existing:
                        goals_by_name[name]["logic"] = new_logic
        all_goals: list[dict] = list(goals_by_name.values())

        all_options: list[dict] = []
        seen_opts: set[str] = set()
        for m in ordered:
            for opt in m.options:
                name = opt.get("name", "")
                if not name or name in seen_opts:
                    continue
                seen_opts.add(name)
                all_options.append(dict(opt))

        all_item_overrides: list[dict] = []
        for m in ordered:
            for ov in m.item_overrides:
                all_item_overrides.append(dict(ov))

        # 6. Compute version string + checksum
        combined_version = ".".join(m.version for m in ordered if m.version) or "0.0.0"
        checksum_payload = json.dumps(
            {"items": all_items, "locations": all_locations}, sort_keys=True
        ).encode("utf-8")
        checksum = hashlib.sha256(checksum_payload).hexdigest()[:16]

        # 7. option_defaults — first-mod-wins for each key
        option_defaults: dict = {}
        for m in ordered:
            for opt in m.options:
                name = opt.get("name", "")
                if name and name not in option_defaults:
                    option_defaults[name] = opt.get("default", 0)

        caps: dict = {
            "version":        combined_version,
            "game":           game,
            "checksum":       checksum,
            "locations":      all_locations,
            "items":          all_items,
        }
        if all_goals:
            caps["goals"] = all_goals
        if option_defaults:
            caps["option_defaults"] = option_defaults
        if all_item_overrides:
            caps["item_overrides"] = all_item_overrides

        return caps

    # ------------------------------------------------------------------
    # Conversion helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _mod_info_to_raw(mod: "ModInfo") -> dict:
        """Convert a ModInfo back to a raw manifest dict for processing."""
        def item_to_dict(it) -> dict:
            d = {"name": it.name, "type": it.type, "amount": it.amount}
            if it.amount_min is not None:
                d["amount_min"] = it.amount_min
            if it.placement:
                d["placement"] = it.placement
            if it.enabled_if:
                d["enabled_if"] = it.enabled_if
            d.update(it.extra)
            return d

        def loc_to_dict(loc) -> dict:
            d = {"name": loc.name}
            if loc.logic:
                d["logic"] = loc.logic
            if loc.out_of_logic:
                d["out_of_logic"] = loc.out_of_logic
            if loc.tags:
                d["tags"] = loc.tags
            d.update(loc.extra)
            return d

        def goal_to_dict(g) -> dict:
            d = {"name": g.name}
            if g.display_name:
                d["display_name"] = g.display_name
            if g.description:
                d["description"] = g.description
            if g.condition:
                d["condition"] = g.condition
            d.update(g.extra)
            return d

        def opt_to_dict(o) -> dict:
            d = {"name": o.name, "type": o.type, "default": o.default}
            if o.description:
                d["description"] = o.description
            d.update(o.extra)
            return d

        def ov_to_dict(ov) -> dict:
            d = {"item_name": ov.item_name, "type": ov.override_type}
            if ov.requires_option:
                d["requires_option"] = ov.requires_option
            d.update(ov.extra)
            return d

        caps: dict = {
            "include":          mod.capabilities_includes,
            "vocab_validation": mod.vocab_validation,
            "items":            [item_to_dict(i) for i in mod.items],
            "locations":        [loc_to_dict(l) for l in mod.locations],
            "goals":            [goal_to_dict(g) for g in mod.goals],
            "options":          [opt_to_dict(o) for o in mod.options],
        }
        return {
            "mod_id":       mod.mod_id,
            "name":         mod.name,
            "version":      mod.version,
            "description":  mod.description,
            "author":       mod.author,
            "depends":      mod.depends,
            "incompatible": mod.incompatible,
            "capabilities": caps,
            "item_overrides": [ov_to_dict(ov) for ov in mod.item_overrides],
        }

    @staticmethod
    def _raw_to_manifest_data(raw: dict, source_path: Optional[Path] = None) -> _ManifestData:
        """Convert a resolved raw manifest dict to _ManifestData."""
        caps = raw.get("capabilities", {})
        return _ManifestData(
            mod_id=raw.get("mod_id", ""),
            name=raw.get("name", ""),
            version=raw.get("version", "0.0.0"),
            depends=raw.get("depends", []),
            incompatible=raw.get("incompatible", []),
            vocab_validation=bool(caps.get("vocab_validation", False)),
            items=caps.get("items", []),
            locations=caps.get("locations", []),
            goals=caps.get("goals", []),
            options=caps.get("options", []),
            item_overrides=raw.get("item_overrides", []),
            source_path=source_path,
        )
