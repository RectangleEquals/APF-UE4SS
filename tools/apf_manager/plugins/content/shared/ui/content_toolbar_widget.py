"""ContentToolbarWidget — toolbar for the Content tab."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText

from .......gui.widgets.tip_icon_button import TipIconButton


class ContentToolbarWidget(MDBoxLayout):
    """
    Toolbar for the Content tab.

    Buttons: Select All | Select None | [spacer] | Refresh | Queue for Download

    Parameters
    ----------
    on_check_all   : Callable[[], None]
    on_uncheck_all : Callable[[], None]
    on_refresh     : Callable[[], None]
    on_queue       : Callable[[], None]
    """

    def __init__(
        self,
        on_check_all: Optional[Callable] = None,
        on_uncheck_all: Optional[Callable] = None,
        on_refresh: Optional[Callable] = None,
        on_queue: Optional[Callable] = None,
        **kwargs,
    ):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            md_bg_color=(0.12, 0.16, 0.20, 1),
            padding=(dp(8), 0),
            spacing=dp(4),
            **kwargs,
        )
        self._btn_check_all = MDButton(
            MDButtonIcon(icon="checkbox-multiple-marked"),
            MDButtonText(text="Select All"),
            style="outlined",
            size_hint=(None, None),
            size=(dp(128), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: on_check_all() if on_check_all else None,
        )
        self._btn_uncheck_all = MDButton(
            MDButtonIcon(icon="checkbox-multiple-blank-outline"),
            MDButtonText(text="Select None"),
            style="outlined",
            size_hint=(None, None),
            size=(dp(128), dp(32)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: on_uncheck_all() if on_uncheck_all else None,
        )
        self._btn_queue = MDButton(
            MDButtonText(text="Queue for Download"),
            style="filled",
            size_hint=(None, None),
            size=(dp(200), dp(36)),
            pos_hint={"center_y": 0.5},
            disabled=True,
            on_release=lambda *_: on_queue() if on_queue else None,
        )

        self.add_widget(self._btn_check_all)
        self.add_widget(self._btn_uncheck_all)
        self.add_widget(Widget(size_hint_x=1))
        self.add_widget(TipIconButton(
            icon="refresh",
            tooltip_text="Refresh registry content",
            on_release=lambda *_: on_refresh() if on_refresh else None,
        ))
        self.add_widget(self._btn_queue)

    def set_queue_enabled(self, enabled: bool) -> None:
        """Enable or disable the Queue for Download button."""
        self._btn_queue.disabled = not enabled
