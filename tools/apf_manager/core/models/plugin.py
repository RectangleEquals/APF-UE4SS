"""
Plugin data classes — PluginContribution and PluginInfo.

Pure model: no Kivy imports, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class PluginContribution:
    type: str                           # "home_screen" | "hub_panel" | "hub_action" | "dialog" | "settings_panel"
    plugin_id: str
    label: str = ""
    icon: str = ""
    priority: int = 50                  # Lower = earlier in nav rail
    panel_class: Any = None             # Widget class for hub_panel / home_screen
    handler: Optional[Callable] = None  # For hub_action / dialog
    dialog_id: str = ""                 # For dialog contributions
    panel_instance: Any = None          # Live instance set by hub after panel creation


@dataclass
class PluginInfo:
    plugin_id: str
    name: str
    version: str
    description: str
    mode: str                           # "player" | "dev" | "both"
    requires: list = field(default_factory=list)
    suggests: list = field(default_factory=list)
    contributions: list = field(default_factory=list)  # raw dicts from plugin.json
    directory: Path = field(default_factory=Path)
    status: str = "pending"            # "pending" | "loaded" | "failed"
    error: str = ""                    # Human-readable failure reason (if status == "failed")
