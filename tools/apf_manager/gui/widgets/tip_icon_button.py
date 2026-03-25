"""
TipIconButton — MDIconButton that accepts a tooltip_text kwarg.

KivyMD 2.x MDTooltip does not support tooltip_text as a constructor
argument (it requires KV). This class accepts the kwarg and discards it
so call sites are future-proof without crashing.
"""

from __future__ import annotations

from kivymd.uix.button import MDIconButton


class TipIconButton(MDIconButton):
    """MDIconButton that silently accepts tooltip_text for future use."""

    def __init__(self, tooltip_text: str = "", **kwargs):
        # tooltip_text stored but not yet wired to KivyMD tooltip machinery
        self._tooltip_text = tooltip_text
        super().__init__(**kwargs)