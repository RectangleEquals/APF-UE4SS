"""
Tab 1 — Registries

Shows:
  - UE4SS setup card (collapsed to status line when UE4SS is detected)
  - "My Registries" cards per user-added URL
  - "Add Registry" URL field (detects share payloads)
  - "Search GitHub" button → discovered repos collapsible list
  - "Share" button → copies base64 registry list to clipboard
"""

from __future__ import annotations

import threading
import webbrowser
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField

if TYPE_CHECKING:
    from ...registry_service import RegistryService


class RegistriesTab(MDBoxLayout):
    """Tab 1 — Registries."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._url_field: Optional[MDTextField] = None
        self._registries_list: Optional[MDBoxLayout] = None
        self._search_results: Optional[MDBoxLayout] = None
        self._ue4ss_card: Optional[MDBoxLayout] = None
        self._add_status: Optional[MDLabel] = None
        self._game_id: str = ""
        self._build_ui()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        scroll = ScrollView(size_hint=(1, 1))
        content = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=[dp(12), dp(8)],
            spacing=dp(12),
        )

        # UE4SS setup card
        self._ue4ss_card = self._build_ue4ss_card()
        content.add_widget(self._ue4ss_card)

        content.add_widget(MDDivider())

        # My Registries section
        content.add_widget(MDLabel(
            text="My Registries",
            font_style="Title",
            role="small",
            size_hint_y=None,
            height=dp(32),
        ))
        self._registries_list = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=dp(8),
        )
        content.add_widget(self._registries_list)

        # Add Registry bar
        add_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            spacing=dp(8),
        )
        self._url_field = MDTextField(
            hint_text="https://github.com/owner/repo  (or paste share code)",
            size_hint=(1, None),
            height=dp(48),
            mode="outlined",
        )
        add_bar.add_widget(self._url_field)
        add_bar.add_widget(MDButton(
            MDButtonText(text="Add"),
            style="filled",
            size_hint=(None, None),
            size=(dp(72), dp(40)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._on_add(),
        ))
        content.add_widget(add_bar)

        self._add_status = MDLabel(
            text="",
            size_hint_y=None,
            height=dp(24),
            theme_text_color="Custom",
            text_color=(0.8, 0.8, 0.8, 1),
        )
        content.add_widget(self._add_status)

        # Action row: Search GitHub + Share
        action_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
        )
        action_row.add_widget(MDButton(
            MDButtonIcon(icon="magnify"),
            MDButtonText(text="Search GitHub"),
            style="outlined",
            on_release=lambda *_: self._on_search_github(),
        ))
        action_row.add_widget(MDButton(
            MDButtonIcon(icon="share-variant"),
            MDButtonText(text="Share"),
            style="outlined",
            on_release=lambda *_: self._on_share(),
        ))
        action_row.add_widget(Widget(size_hint=(1, 1)))
        content.add_widget(action_row)

        # Search results (hidden until search runs)
        self._search_results = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=dp(6),
        )
        content.add_widget(self._search_results)

        scroll.add_widget(content)
        self.add_widget(scroll)

    def _build_ue4ss_card(self) -> MDBoxLayout:
        card = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=[dp(8), dp(8)],
            spacing=dp(4),
            md_bg_color=(0.1, 0.14, 0.18, 1),
        )
        card.add_widget(MDLabel(
            text="UE4SS",
            font_style="Label",
            role="medium",
            size_hint_y=None,
            height=dp(24),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        ))
        self._ue4ss_status_lbl = MDLabel(
            text="Checking…",
            size_hint_y=None,
            height=dp(24),
        )
        card.add_widget(self._ue4ss_status_lbl)
        return card

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def refresh(self, game_id: str, ue4ss_detected: bool) -> None:
        self._game_id = game_id
        self._refresh_ue4ss_card(ue4ss_detected)
        self._refresh_registries()

    def _refresh_ue4ss_card(self, ue4ss_detected: bool) -> None:
        if ue4ss_detected:
            self._ue4ss_status_lbl.text = "✓ UE4SS detected"
            self._ue4ss_status_lbl.theme_text_color = "Custom"
            self._ue4ss_status_lbl.text_color = (0.3, 0.8, 0.4, 1)
        else:
            self._ue4ss_status_lbl.text = "⚠ UE4SS not detected"
            self._ue4ss_status_lbl.theme_text_color = "Custom"
            self._ue4ss_status_lbl.text_color = (0.9, 0.6, 0.1, 1)

    def _refresh_registries(self) -> None:
        self._registries_list.clear_widgets()
        svc = self._registry_svc()
        if not svc:
            self._registries_list.add_widget(MDLabel(
                text="Registry service unavailable.",
                size_hint_y=None,
                height=dp(32),
            ))
            return

        entries = svc.get_user_registries()
        if not entries:
            self._registries_list.add_widget(MDLabel(
                text="No registries added yet.",
                size_hint_y=None,
                height=dp(32),
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            return

        for entry in entries:
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(48),
                spacing=dp(8),
            )
            row.add_widget(MDLabel(
                text=f"{entry.owner}/{entry.repo}",
                size_hint=(1, 1),
            ))
            row.add_widget(MDButton(
                MDButtonText(text="Report"),
                style="text",
                size_hint=(None, None),
                size=(dp(72), dp(36)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, u=entry.url: self._on_report(u),
            ))
            row.add_widget(MDIconButton(
                icon="refresh",
                on_release=lambda *_, e=entry: self._on_refresh_one(e),
            ))
            row.add_widget(MDIconButton(
                icon="delete",
                on_release=lambda *_, e=entry: self._on_remove(e),
            ))
            self._registries_list.add_widget(row)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_add(self) -> None:
        url = (self._url_field.text or "").strip()
        if not url:
            return

        svc = self._registry_svc()
        if not svc:
            return

        # Detect share payload
        if svc.is_share_payload(url):
            urls = svc.import_registries_b64(url)
            self._show_import_dialog(urls)
            return

        self._set_add_status("Adding…", (0.7, 0.7, 0.7, 1))
        svc.add_registry(url, on_done=self._on_add_done)

    def _on_add_done(self, success: bool, msg: str) -> None:
        color = (0.3, 0.8, 0.4, 1) if success else (0.9, 0.3, 0.3, 1)
        self._set_add_status(msg, color)
        if success:
            self._url_field.text = ""
            self._refresh_registries()

    def _set_add_status(self, text: str, color) -> None:
        if self._add_status:
            self._add_status.text = text
            self._add_status.text_color = color

    def _on_remove(self, entry) -> None:
        svc = self._registry_svc()
        if svc:
            svc.remove_registry(entry.url)
        self._refresh_registries()

    def _on_refresh_one(self, entry) -> None:
        svc = self._registry_svc()
        if svc:
            svc.refresh_all(on_done=self._refresh_registries)

    def _on_report(self, url: str) -> None:
        issue_url = (
            "https://github.com/RectangleEquals/APF-UE4SS/issues/new"
            "?title=Registry+blacklist+request"
            f"&body=Please+add+this+registry+to+the+blocklist:%0A{url}"
        )
        webbrowser.open(issue_url)

    def _on_search_github(self) -> None:
        svc = self._registry_svc()
        if not svc or not self._game_id:
            return
        self._search_results.clear_widgets()
        self._search_results.add_widget(MDLabel(
            text="Searching GitHub…",
            size_hint_y=None,
            height=dp(32),
        ))
        svc.search_github(self._game_id, on_done=self._on_search_results)

    def _on_search_results(self, results: list) -> None:
        self._search_results.clear_widgets()
        if not results:
            self._search_results.add_widget(MDLabel(
                text="No public registries found for this game.",
                size_hint_y=None,
                height=dp(32),
            ))
            return
        self._search_results.add_widget(MDLabel(
            text=f"Found {len(results)} public registry repo(s):",
            font_style="Label",
            size_hint_y=None,
            height=dp(28),
        ))
        for r in results:
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(40),
                spacing=dp(8),
            )
            row.add_widget(MDLabel(
                text=f"{r['owner']}/{r['repo']}  ★{r['stars']}",
                size_hint=(1, 1),
            ))
            row.add_widget(MDButton(
                MDButtonText(text="Add"),
                style="filled",
                size_hint=(None, None),
                size=(dp(64), dp(32)),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, url=r["html_url"]: self._on_add_from_search(url),
            ))
            self._search_results.add_widget(row)

    def _on_add_from_search(self, url: str) -> None:
        self._url_field.text = url
        self._on_add()

    def _on_share(self) -> None:
        svc = self._registry_svc()
        if not svc:
            return
        encoded = svc.export_registries_b64()
        Clipboard.copy(encoded)
        self._set_add_status("Registry list copied to clipboard.", (0.3, 0.8, 0.4, 1))

    def _show_import_dialog(self, urls: list[str]) -> None:
        if not urls:
            self._set_add_status("No registries found in share payload.", (0.9, 0.6, 0.1, 1))
            return

        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )

        svc = self._registry_svc()
        if not svc:
            return

        def _add_all(*_):
            dlg.dismiss()
            for url in urls:
                svc.add_registry(url, on_done=lambda s, m: None)
            self._refresh_registries()
            self._url_field.text = ""

        def _dismiss(*_):
            dlg.dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Import Registries"),
            MDDialogSupportingText(
                text=f"Found {len(urls)} registr{'y' if len(urls) == 1 else 'ies'}. Add all?"
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_dismiss),
                MDButton(MDButtonText(text="Add All"), style="filled", on_release=_add_all),
            ),
        )
        dlg.open()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _registry_svc(self) -> Optional["RegistryService"]:
        if self._host.has_service("registry"):
            return self._host.get_service("registry")
        return None
