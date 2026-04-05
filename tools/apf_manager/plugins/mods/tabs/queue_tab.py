"""
Tab 4 — Queue

Shows:
  - Staged mods list with auto-resolved deps
  - Conflicts panel (collapsible, red when errors present)
  - Framework mod confirmation
  - Load order preview (post-install)
  - "Install All" button (disabled with unresolved errors)

Disabled until at least 1 mod is staged.
"""

from __future__ import annotations

import threading
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel

if TYPE_CHECKING:
    from ...registry_service import RegistryService


class QueueTab(MDBoxLayout):
    """Tab 4 — Queue (review and install staged mods)."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._content: Optional[MDBoxLayout] = None
        self._install_btn: Optional[MDButton] = None
        self._status_lbl: Optional[MDLabel] = None
        self._game_id: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = ScrollView(size_hint=(1, 1))
        self._content = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=[dp(12), dp(8)],
            spacing=dp(12),
        )
        scroll.add_widget(self._content)
        self.add_widget(scroll)

        # Bottom action bar
        action_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            padding=[dp(12), dp(8)],
            spacing=dp(12),
            md_bg_color=(0.1, 0.12, 0.14, 1),
        )
        self._status_lbl = MDLabel(
            text="",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        action_bar.add_widget(self._status_lbl)
        self._install_btn = MDButton(
            MDButtonText(text="Install All"),
            style="filled",
            size_hint=(None, None),
            size=(dp(120), dp(40)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._on_install(),
        )
        action_bar.add_widget(self._install_btn)
        self.add_widget(action_bar)

    def refresh(self, game_id: str) -> None:
        self._game_id = game_id
        self._content.clear_widgets()
        svc = self._registry_svc()

        if not svc:
            return

        staged = svc.get_staged()
        if not staged:
            self._content.add_widget(MDLabel(
                text="No mods staged. Go to the Mods tab to stage mods for install.",
                halign="center",
                size_hint_y=None,
                height=dp(60),
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            if self._install_btn:
                self._install_btn.disabled = True
            return

        # Staged mods list
        self._content.add_widget(MDLabel(
            text="Staged Mods",
            font_style="Title",
            role="small",
            size_hint_y=None,
            height=dp(32),
        ))
        for mod in staged:
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(36),
                spacing=dp(8),
            )
            row.add_widget(MDLabel(
                text=f"  {mod.name or mod.mod_id}",
                size_hint=(1, 1),
            ))
            row.add_widget(MDLabel(
                text=mod.mod_id,
                size_hint=(None, 1),
                width=dp(200),
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            self._content.add_widget(row)

        # Validation
        errors = svc.validate_queue(game_id)
        blocking = [e for e in errors if e.severity == "error"]

        if errors:
            self._content.add_widget(MDLabel(
                text="Issues",
                font_style="Title",
                role="small",
                size_hint_y=None,
                height=dp(32),
                theme_text_color="Custom",
                text_color=(0.9, 0.3, 0.3, 1) if blocking else (0.9, 0.6, 0.1, 1),
            ))
            for e in errors:
                icon = "✗" if e.severity == "error" else "⚠"
                color = (0.9, 0.3, 0.3, 1) if e.severity == "error" else (0.9, 0.6, 0.1, 1)
                self._content.add_widget(MDLabel(
                    text=f"{icon} {e.message}",
                    size_hint_y=None,
                    height=dp(28),
                    theme_text_color="Custom",
                    text_color=color,
                ))

        if self._install_btn:
            self._install_btn.disabled = bool(blocking)
        if self._status_lbl:
            self._status_lbl.text = f"{len(staged)} mod(s) ready" if not blocking else "Resolve errors before installing"

    def _on_install(self) -> None:
        svc = self._registry_svc()
        if not svc:
            return
        if self._status_lbl:
            self._status_lbl.text = "Installing…"
        if self._install_btn:
            self._install_btn.disabled = True

        def _progress(msg: str):
            if self._status_lbl:
                self._status_lbl.text = msg

        def _done(success: bool, msg: str):
            if self._status_lbl:
                color = (0.3, 0.8, 0.4, 1) if success else (0.9, 0.3, 0.3, 1)
                self._status_lbl.text = msg
                self._status_lbl.text_color = color
            self.refresh(self._game_id)

        svc.install_queue(self._game_id, on_progress=_progress, on_done=_done)

    def _registry_svc(self) -> Optional["RegistryService"]:
        if self._host.has_service("registry"):
            return self._host.get_service("registry")
        return None
