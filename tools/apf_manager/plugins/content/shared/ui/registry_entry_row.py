"""RegistryEntryRow — single user-added registry entry row."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel


class RegistryEntryRow(MDBoxLayout):
    """
    Row for a single user-added registry entry.

    Parameters
    ----------
    entry       : registry entry object with .repo.full_name and .url
    on_view     : Callable[[entry], None]
    on_report   : Callable[[str], None] — called with entry.url
    on_refresh  : Callable[[entry], None]
    on_remove   : Callable[[entry], None]
    """

    def __init__(
        self,
        entry,
        on_view: Optional[Callable] = None,
        on_report: Optional[Callable] = None,
        on_refresh: Optional[Callable] = None,
        on_remove: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
            **kwargs,
        )
        self.add_widget(MDLabel(text=entry.repo.full_name, size_hint=(1, 1)))
        self.add_widget(MDIconButton(
            icon="eye",
            theme_icon_color="Custom",
            icon_color=(0.5, 0.75, 1.0, 1),
            on_release=lambda *_: on_view(entry) if on_view else None,
        ))
        self.add_widget(MDIconButton(
            icon="flag",
            theme_icon_color="Custom",
            icon_color=(0.9, 0.2, 0.2, 1),
            on_release=lambda *_: on_report(entry.url) if on_report else None,
        ))
        self.add_widget(MDIconButton(
            icon="refresh",
            on_release=lambda *_: on_refresh(entry) if on_refresh else None,
        ))
        self.add_widget(MDIconButton(
            icon="delete",
            on_release=lambda *_: on_remove(entry) if on_remove else None,
        ))
