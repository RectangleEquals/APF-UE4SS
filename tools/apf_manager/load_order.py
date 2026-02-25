"""
APF Manager — mods.txt load order manager.

mods.txt structure:
  [any mix of AP and non-AP mod entries]
  ; Built-in keybinds, do not move up!   ← PROTECTED FOOTER (never modify)
  Keybinds : 1

The tool manages all entries above the footer. Within the AP mods:
  - APFrameworkMod must always be first (hard constraint)
  - All other ordering issues are warnings only
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_ENTRY_RE = re.compile(r"^\s*([A-Za-z0-9_\-\.]+)\s*:\s*([01])\s*$")
FOOTER_SENTINEL = "; Built-in keybinds, do not move up!"
FRAMEWORK_MOD = "APFrameworkMod"


@dataclass
class ModsEntry:
    name: str
    enabled: bool           # True = ": 1", False = ": 0"
    raw_line: str           # Original line text (preserves whitespace)
    is_ap_mod: bool = False # Set by caller after cross-referencing ModDiscovery
    folder_exists: bool = False


def _parse_line(line: str) -> tuple[str, bool] | None:
    """Parse 'ModName : 1' or 'ModName : 0'. Returns (name, enabled) or None."""
    m = _ENTRY_RE.match(line)
    if m:
        return m.group(1), m.group(2) == "1"
    return None


class ModsTextManager:
    """
    Read/write mods.txt while preserving comments, blank lines, and the protected footer.
    All AP vs non-AP classification is done by the caller via known_ap_mods.
    """

    def parse(self, path: Path, known_ap_mods: set[str]) -> tuple[list[ModsEntry | str], list[str]]:
        """
        Parse mods.txt into (body, footer).

        body: list of ModsEntry (for mod entries) or str (for comment/blank lines)
        footer: list of raw lines from FOOTER_SENTINEL to end of file (verbatim)
        """
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        footer_start = None
        for i, line in enumerate(lines):
            if line.rstrip("\n\r") == FOOTER_SENTINEL:
                footer_start = i
                break

        body_lines = lines[:footer_start] if footer_start is not None else lines
        footer_lines = lines[footer_start:] if footer_start is not None else []

        body: list[ModsEntry | str] = []
        for line in body_lines:
            stripped = line.rstrip("\n\r")
            parsed = _parse_line(stripped)
            if parsed:
                name, enabled = parsed
                entry = ModsEntry(
                    name=name,
                    enabled=enabled,
                    raw_line=line,
                    is_ap_mod=name in known_ap_mods,
                    folder_exists=False,  # caller fills this in
                )
                body.append(entry)
            else:
                body.append(stripped + ("\n" if not stripped.endswith("\n") else ""))

        return body, footer_lines

    def write(self, path: Path, body: list[ModsEntry | str], footer_lines: list[str]) -> None:
        """Write body entries then footer, preserving original line endings."""
        lines: list[str] = []
        for item in body:
            if isinstance(item, ModsEntry):
                flag = "1" if item.enabled else "0"
                lines.append(f"{item.name} : {flag}\n")
            else:
                lines.append(item if item.endswith("\n") else item + "\n")
        lines.extend(footer_lines)
        path.write_text("".join(lines), encoding="utf-8")

    def add_mod(self, path: Path, mod_name: str, known_ap_mods: set[str]) -> None:
        """
        Add a new AP mod entry to the body, just before the footer.
        APFrameworkMod is always placed first among all AP mod entries.
        If mod_name already exists in the file, do nothing.
        """
        body, footer = self.parse(path, known_ap_mods)

        # Check if already present
        existing_names = {e.name for e in body if isinstance(e, ModsEntry)}
        if mod_name in existing_names:
            return

        new_entry = ModsEntry(
            name=mod_name,
            enabled=True,
            raw_line=f"{mod_name} : 1\n",
            is_ap_mod=True,
            folder_exists=True,
        )

        if mod_name == FRAMEWORK_MOD:
            # Insert before the first existing AP mod entry (or before footer if none)
            insert_at = 0
            for i, item in enumerate(body):
                if isinstance(item, ModsEntry) and item.is_ap_mod:
                    insert_at = i
                    break
            else:
                insert_at = len(body)
            body.insert(insert_at, new_entry)
        else:
            # Insert just before the footer (append to end of body)
            body.append(new_entry)

        self.write(path, body, footer)

    def remove_mod(self, path: Path, mod_name: str, known_ap_mods: set[str]) -> None:
        """Remove a mod entry by name. No-op if not found."""
        body, footer = self.parse(path, known_ap_mods)
        body = [item for item in body
                if not (isinstance(item, ModsEntry) and item.name == mod_name)]
        self.write(path, body, footer)

    def reorder(self, path: Path, new_ap_order: list[str], known_ap_mods: set[str]) -> None:
        """
        Reorder AP mod entries in the body to match new_ap_order.
        Non-AP entries stay in their original relative positions.
        APFrameworkMod is always kept first — if it's not first in new_ap_order, it is moved there.
        """
        body, footer = self.parse(path, known_ap_mods)

        # Build ordered AP-mod entry map
        ap_entries: dict[str, ModsEntry] = {}
        for item in body:
            if isinstance(item, ModsEntry) and item.is_ap_mod:
                ap_entries[item.name] = item

        # Enforce APFrameworkMod first
        ordered = list(new_ap_order)
        if FRAMEWORK_MOD in ordered:
            ordered.remove(FRAMEWORK_MOD)
        if FRAMEWORK_MOD in ap_entries:
            ordered.insert(0, FRAMEWORK_MOD)

        # Build new body: non-AP entries keep their positions;
        # AP entry slots are replaced in the new order.
        ap_iter = iter(ordered)
        new_body: list[ModsEntry | str] = []
        for item in body:
            if isinstance(item, ModsEntry) and item.is_ap_mod:
                name = next(ap_iter, None)
                if name and name in ap_entries:
                    new_body.append(ap_entries[name])
            else:
                new_body.append(item)

        self.write(path, new_body, footer)

    def get_entries(self, path: Path, known_ap_mods: set[str]) -> list[ModsEntry]:
        """Return only ModsEntry objects (excluding comment/blank lines) from the body."""
        body, _ = self.parse(path, known_ap_mods)
        return [item for item in body if isinstance(item, ModsEntry)]
