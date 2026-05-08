from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def parse_vdf(text: str) -> dict:
    """
    Minimal Valve Data Format (VDF) parser.
    Handles flat key-value and one level of nested blocks.
    """
    root: dict = {}
    stack: list[dict] = [root]
    key: Optional[str] = None

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue

        if stripped == "{":
            if key is not None:
                new_dict: dict = {}
                stack[-1][key] = new_dict
                stack.append(new_dict)
                key = None
            continue

        if stripped == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
            continue

        m = re.match(r'"([^"]*)"(?:\s+"([^"]*)")?', stripped)
        if m:
            k = m.group(1)
            v = m.group(2)
            if v is None:
                key = k
            else:
                stack[-1][k] = v
                key = None

    return root


@dataclass
class SteamGame:
    app_id: int
    name: str
    install_dir: Path
    is_ue: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return self.name
