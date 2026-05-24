"""
ModsTextManager — parse and write UE4SS mods.txt.

Format:
    ModName : 1    (enabled)
    ModName : 0    (disabled)
    ; comment

Protected footer (at absolute bottom when present, never moved):
    ; Built-in keybinds, do not move up!
    Keybinds : 1

The footer is preserved only if it already existed in the file being read.
Some UE4SS versions omit it — this is handled transparently.

Framework mod ordering is enforced via enforce_ap_ordering(), called by DeployService
after each AP mod deploy to maintain the APFrameworkMod-first invariant.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


_FOOTER_LINES = [
    "; Built-in keybinds, do not move up!",
    "Keybinds : 1",
]


class ModEntry:
    __slots__ = ("name", "enabled")

    def __init__(self, name: str, enabled: bool) -> None:
        self.name = name
        self.enabled = enabled

    def __repr__(self) -> str:
        return f"ModEntry({self.name!r}, {self.enabled})"


class ModsTextManager:
    """
    In-memory representation of mods.txt with read/write support.

    Load:  manager = ModsTextManager(path); manager.load()
    Edit:  manager.set_enabled("MyMod", True)
    Save:  manager.save()
    """

    def __init__(self, mods_txt: Path) -> None:
        self._path = mods_txt
        self._entries: list[ModEntry] = []   # ordered list (footer excluded)
        self._comments: list[str] = []       # comment lines (preserved as-is, at top)
        self._raw_comments: list[str] = []   # leading comment lines before first entry
        self._has_footer: bool = False       # True if the file contained the keybinds footer

    # -----------------------------------------------------------------------
    # Load
    # -----------------------------------------------------------------------

    def load(self) -> None:
        self._entries = []
        self._raw_comments = []
        self._has_footer = False

        if not self._path.exists():
            return

        lines = self._path.read_text(encoding="utf-8").splitlines()

        # Strip footer from bottom before parsing
        footer_start = self._find_footer(lines)
        self._has_footer = footer_start < len(lines)
        body = lines[:footer_start]

        in_header = True
        for line in body:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(";"):
                if in_header:
                    self._raw_comments.append(line)
                continue
            in_header = False
            entry = self._parse_entry(stripped)
            if entry:
                self._entries.append(entry)

    @staticmethod
    def _parse_entry(line: str) -> Optional[ModEntry]:
        """Parse 'Name : 0' or 'Name : 1'."""
        if " : " not in line:
            return None
        parts = line.split(" : ", 1)
        name = parts[0].strip()
        try:
            enabled = bool(int(parts[1].strip()))
        except ValueError:
            enabled = False
        return ModEntry(name=name, enabled=enabled)

    @staticmethod
    def _find_footer(lines: list[str]) -> int:
        """Return index of the first footer line, or len(lines) if absent."""
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip()
            if stripped in _FOOTER_LINES:
                # Walk back to find the start of the footer block
                start = i
                while start > 0 and lines[start - 1].strip() in _FOOTER_LINES:
                    start -= 1
                return start
        return len(lines)

    # -----------------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------------

    @property
    def entries(self) -> list[ModEntry]:
        return list(self._entries)

    @property
    def has_footer(self) -> bool:
        """True if the keybinds footer was present in the file when loaded."""
        return self._has_footer

    def get_order(self) -> list[str]:
        return [e.name for e in self._entries]

    def contains(self, name: str) -> bool:
        """True if the name appears in mods.txt (regardless of enabled state)."""
        return self._find(name) is not None

    def is_enabled(self, name: str) -> bool:
        entry = self._find(name)
        return entry.enabled if entry else False

    def _find(self, name: str) -> Optional[ModEntry]:
        return next((e for e in self._entries if e.name == name), None)

    # -----------------------------------------------------------------------
    # Mutate
    # -----------------------------------------------------------------------

    def set_enabled(self, name: str, enabled: bool) -> None:
        entry = self._find(name)
        if entry:
            entry.enabled = enabled

    def ensure_entry(self, name: str, enabled: bool = True) -> None:
        """Add entry if not already present."""
        if not self._find(name):
            self._entries.append(ModEntry(name=name, enabled=enabled))

    def remove_entry(self, name: str) -> None:
        self._entries = [e for e in self._entries if e.name != name]

    def reorder(self, names: list[str]) -> None:
        """
        Reorder entries to match the given name list.
        Names not in the list are appended at the end in original order.
        Framework mod ordering is enforced by DeployService before calling this.
        """
        name_set = set(names)
        ordered = []
        name_to_entry = {e.name: e for e in self._entries}

        for n in names:
            if n in name_to_entry:
                ordered.append(name_to_entry[n])

        # Append anything not in the provided list
        for e in self._entries:
            if e.name not in name_set:
                ordered.append(e)

        self._entries = ordered

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------

    def enforce_ap_ordering(self, mods_dir: "Path") -> bool:
        """Ensure APFrameworkMod precedes all other AP mods in the entry list.

        Reads manifest.json from each entry's mod folder to determine whether it
        is an AP mod (has 'mod_id') and whether it is the framework mod
        (mod_id matches 'archipelago.<game>.framework').

        Returns True if entries were reordered, False if the order was already correct.
        Only rewrites in-memory entries; the caller must call save() afterwards.
        """
        import json
        import re
        _FRAMEWORK_RE = re.compile(r"^archipelago\.[a-z0-9_]+\.framework$")

        def _mod_id(name: str) -> str:
            try:
                manifest = mods_dir / name / "manifest.json"
                if manifest.exists():
                    return json.loads(manifest.read_text(encoding="utf-8")).get("mod_id", "")
            except Exception:
                pass
            return ""

        # Locate the framework mod entry index
        fw_idx = -1
        fw_entry = None
        for i, entry in enumerate(self._entries):
            mid = _mod_id(entry.name)
            if mid and _FRAMEWORK_RE.match(mid):
                fw_idx = i
                fw_entry = entry
                break

        if fw_entry is None:
            return False  # No framework mod in mods.txt — nothing to enforce

        # Find the first AP mod entry that appears before the framework mod
        first_ap_before_fw = -1
        for i in range(fw_idx):
            mid = _mod_id(self._entries[i].name)
            if mid and not _FRAMEWORK_RE.match(mid):
                first_ap_before_fw = i
                break

        if first_ap_before_fw == -1:
            return False  # Framework already leads all AP mods

        # Move framework mod to just before the first AP mod that precedes it
        self._entries.pop(fw_idx)
        self._entries.insert(first_ap_before_fw, fw_entry)
        return True

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        for comment in self._raw_comments:
            lines.append(comment)

        for entry in self._entries:
            lines.append(f"{entry.name} : {1 if entry.enabled else 0}")

        # Only write the keybinds footer if it was present when the file was loaded
        if self._has_footer:
            lines.append("")
            for fl in _FOOTER_LINES:
                lines.append(fl)

        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")
