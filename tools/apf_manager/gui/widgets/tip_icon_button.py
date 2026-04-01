"""
TipIconButton — MDIconButton that accepts a tooltip_text kwarg.

KivyMD 2.x MDTooltip does not support tooltip_text as a constructor
argument (it requires KV). This class accepts the kwarg and discards it
so call sites are future-proof without crashing.
"""

from __future__ import annotations

from pathlib import Path

from kivy.metrics import dp
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image as KivyImage
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel


class TipIconButton(MDIconButton):
    """MDIconButton that silently accepts tooltip_text for future use."""

    def __init__(self, tooltip_text: str = "", **kwargs):
        # tooltip_text stored but not yet wired to KivyMD tooltip machinery
        self._tooltip_text = tooltip_text
        super().__init__(**kwargs)


class ImageIconButton(ButtonBehavior, MDBoxLayout):
    """
    Icon button backed by a PNG image instead of a Material Design font icon.
    Size matches MDIconButton defaults (dp(40) × dp(40)).
    Callers handle on_release and URL opening — no webbrowser dependency here.
    """

    def __init__(self, source: str, tooltip_text: str = "", **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(40), dp(40)))
        kwargs.setdefault("padding", [dp(8), dp(8)])
        super().__init__(**kwargs)
        self._tooltip_text = tooltip_text
        self.add_widget(KivyImage(source=source, size_hint=(1, 1), fit_mode="contain"))


class ImageTextButton(ButtonBehavior, MDBoxLayout):
    """
    Button with a PNG image + text label.

    Use where MDButton cannot render KivyImage children (KivyMD 2.x MDButton
    only positions MDButtonIcon/MDButtonText/MDButtonLeadingIcon children).
    The image is omitted if the path does not exist or is empty.
    """

    def __init__(self, source: str = "", text: str = "", **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("adaptive_height", True)
        kwargs.setdefault("adaptive_width", True)
        kwargs.setdefault("spacing", dp(8))
        kwargs.setdefault("padding", [dp(16), dp(10)])
        super().__init__(**kwargs)
        if source and Path(source).exists():
            self.add_widget(KivyImage(
                source=source,
                size_hint=(None, None),
                size=(dp(20), dp(20)),
                fit_mode="contain",
            ))
        self.add_widget(MDLabel(
            text=text,
            adaptive_height=True,
            adaptive_width=True,
            valign="middle",
        ))