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

import webbrowser
from typing import Optional

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivymd.uix.textfield import MDTextField

from ..rows.registry_entry_row import RegistryEntryRow
from ..cards.search_result_card import SearchResultCard, search_score
from ..cards.ue4ss_status_card import UE4SSStatusCard
from ..dialogs.rate_limit_dialog import RateLimitDialog


class RegistriesTab(MDBoxLayout):
    """Tab 1 — Registries."""

    def __init__(self, host, on_registry_changed=None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._on_registry_changed = on_registry_changed
        self._url_field: Optional[MDTextField] = None
        self._registries_list: Optional[MDBoxLayout] = None
        self._search_results: Optional[MDBoxLayout] = None
        self._ue4ss_card: Optional[UE4SSStatusCard] = None
        self._add_status: Optional[MDLabel] = None
        self._add_btn: Optional[MDButton] = None
        self._search_github_btn: Optional[MDButton] = None
        self._share_btn: Optional[MDButton] = None
        self._game_id: str = ""
        self._viewer_in_flight: bool = False
        self._entry_rows: list = []
        from ...controllers.tabs.registries.controller import RegistriesController
        self._ctrl = RegistriesController(host)
        self._build_ui()
        self._wire_rate_limit_callbacks()

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

        content.add_widget(MDLabel(
            text=(
                "Registries are GitHub repositories that contain AP mods for your game. "
                "Add a registry URL below to browse and install mods, or search GitHub "
                "to discover community registries and share your list with others."
            ),
            size_hint_y=None,
            adaptive_height=True,
            theme_text_color="Secondary",
            font_style="Body",
            role="small",
        ))

        # UE4SS setup card
        self._ue4ss_card = UE4SSStatusCard()
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
        self._add_btn = MDButton(
            MDButtonText(text="View"),
            style="filled",
            size_hint=(None, None),
            size=(dp(72), dp(40)),
            pos_hint={"center_y": 0.5},
            on_release=lambda *_: self._on_add(),
        )
        add_bar.add_widget(self._add_btn)
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
        self._search_github_btn = MDButton(
            MDButtonIcon(icon="magnify"),
            MDButtonText(text="Search GitHub"),
            style="outlined",
            on_release=lambda *_: self._on_search_github(),
        )
        action_row.add_widget(self._search_github_btn)
        self._share_btn = MDButton(
            MDButtonIcon(icon="share-variant"),
            MDButtonText(text="Share"),
            style="outlined",
            disabled=True,
            on_release=lambda *_: self._on_share(),
        )
        action_row.add_widget(self._share_btn)
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

    def _wire_rate_limit_callbacks(self) -> None:
        self._ctrl.set_rate_limit_callbacks(
            on_rate_limit=self._on_rate_limit,
            on_search_rate_limit=self._on_search_rate_limit,
        )

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def refresh(self, game_id: str, ue4ss_detected: bool) -> None:
        self._game_id = game_id
        if self._search_results is not None:
            self._search_results.clear_widgets()
        self._refresh_ue4ss_card(ue4ss_detected)
        self._refresh_registries()
        self._wire_rate_limit_callbacks()

    def _refresh_ue4ss_card(self, ue4ss_detected: bool) -> None:
        if not self._ue4ss_card:
            return
        self._ue4ss_card.refresh(ue4ss_detected, self._ctrl.get_ue4ss_update_info())

    def _refresh_registries(self) -> None:
        self._entry_rows.clear()
        self._registries_list.clear_widgets()
        if not self._host.has_service("registry"):
            self._registries_list.add_widget(MDLabel(
                text="Registry service unavailable.",
                size_hint_y=None,
                height=dp(32),
            ))
            return

        entries = self._ctrl.get_user_registries(self._game_id)
        if self._share_btn:
            self._share_btn.disabled = not bool(entries)
        if not entries:
            self._registries_list.add_widget(MDLabel(
                text=(
                    "No registries added for this game yet.\n"
                    "Paste a GitHub repository URL in the field below, "
                    "or click Search GitHub to discover community registries."
                ),
                size_hint_y=None,
                adaptive_height=True,
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))
            return

        for entry in entries:
            row = RegistryEntryRow(
                entry=entry,
                on_view=self._on_view,
                on_report=self._on_report,
                on_refresh=self._on_refresh_one,
                on_remove=self._on_remove,
            )
            self._entry_rows.append(row)
            self._registries_list.add_widget(row)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_add(self) -> None:
        url = (self._url_field.text or "").strip()
        if not url:
            return

        if self._ctrl.is_share_payload(url):
            urls = self._ctrl.import_registries_b64(url)
            self._show_import_dialog(urls)
            return

        from ...controllers.registry.resolver import parse_github_url
        parsed = parse_github_url(url)
        if parsed:
            owner, repo = parsed
            if self._ctrl.is_blacklisted(owner, repo):
                self._set_add_status("This repository is on the block list.", (0.9, 0.3, 0.3, 1))
                return

        self._start_view(url, self._on_add_done)

    def _on_add_done(self, success: bool, msg: str) -> None:
        color = (0.3, 0.8, 0.4, 1) if success else (0.9, 0.3, 0.3, 1)
        self._set_add_status(msg, color)
        if success:
            self._url_field.text = ""
            self._refresh_registries()
            if self._on_registry_changed:
                self._on_registry_changed()
            if hasattr(self._host, "notify_state_change"):
                self._host.notify_state_change("registry")

    def _set_add_status(self, text: str, color) -> None:
        if self._add_status:
            self._add_status.text = text
            self._add_status.text_color = color

    def _on_view(self, entry) -> None:
        self._start_view(entry.url, self._on_view_done)

    def _on_view_done(self, ok: bool, msg: str) -> None:
        self._set_add_status("" if ok else msg, (0.9, 0.3, 0.3, 1))

    # -----------------------------------------------------------------------
    # Viewer in-flight guard
    # -----------------------------------------------------------------------

    def _start_view(self, url: str, on_done) -> None:
        if self._viewer_in_flight:
            return
        self._viewer_in_flight = True
        self._set_all_view_buttons_enabled(False)
        self._set_add_status("Loading\u2026", (0.7, 0.7, 0.7, 1))
        self._ctrl.add_registry(url, self._game_id, on_done=self._wrap_view_done(on_done))

    def _wrap_view_done(self, callback) -> callable:
        def _done(ok: bool, msg: str) -> None:
            self._viewer_in_flight = False
            self._set_all_view_buttons_enabled(True)
            callback(ok, msg)
        return _done

    def _set_all_view_buttons_enabled(self, enabled: bool) -> None:
        if self._add_btn:
            self._add_btn.disabled = not enabled
        for row in self._entry_rows:
            row.set_view_enabled(enabled)

    def _on_remove(self, entry) -> None:
        self._ctrl.remove_registry(entry.url)
        self._refresh_registries()
        self._show_snackbar("Registry removed.")
        if self._on_registry_changed:
            self._on_registry_changed()
        if hasattr(self._host, "notify_state_change"):
            self._host.notify_state_change("registry")

    def _on_refresh_one(self, entry) -> None:
        self._set_add_status("Refreshing\u2026", (0.7, 0.7, 0.7, 1))

        def _on_refresh_done():
            self._set_add_status("", (0.7, 0.7, 0.7, 1))
            self._refresh_registries()
            self._show_snackbar("Registries refreshed.")
            if self._on_registry_changed:
                self._on_registry_changed()

        self._ctrl.refresh_all(on_done=_on_refresh_done)

    def _on_report(self, url: str) -> None:
        issue_url = (
            "https://github.com/RectangleEquals/APF-UE4SS/issues/new"
            "?title=Registry+blacklist+request"
            f"&body=Please+add+this+registry+to+the+blocklist:%0A{url}"
        )
        webbrowser.open(issue_url)

    def _on_search_github(self) -> None:
        if not self._game_id:
            return
        if self._search_github_btn:
            self._search_github_btn.disabled = True
        self._search_results.clear_widgets()
        self._search_results.add_widget(MDLabel(
            text="Searching GitHub\u2026",
            size_hint_y=None,
            height=dp(32),
        ))
        self._ctrl.search_github(
            self._game_id,
            on_done=lambda results: Clock.schedule_once(
                lambda dt: self._on_search_results(results), 0
            ),
        )

    def _on_search_results(self, results: list) -> None:
        if self._search_github_btn:
            self._search_github_btn.disabled = False
        self._search_results.clear_widgets()
        if not results:
            self._search_results.add_widget(MDLabel(
                text="No public registries found for this game.",
                size_hint_y=None,
                height=dp(32),
            ))
            return

        results = sorted(results, key=search_score, reverse=True)

        self._search_results.add_widget(MDLabel(
            text=f"Found {len(results)} public registry repo(s):",
            font_style="Label",
            size_hint_y=None,
            height=dp(28),
        ))
        existing_urls: set = set()
        for entry in self._ctrl.get_user_registries(self._game_id):
            existing_urls.add(entry.url.rstrip("/").lower())

        for r in results:
            owner, repo = r["owner"], r["repo"]
            is_bl = self._ctrl.is_blacklisted(owner, repo)
            html_url = r.get("html_url", "")
            is_added = html_url.rstrip("/").lower() in existing_urls
            if is_bl:
                self._host.log(
                    f"[registry] [WARN] Search result {owner}/{repo} is blacklisted — Add disabled"
                )
            self._search_results.add_widget(SearchResultCard(
                result=r,
                is_blacklisted=is_bl,
                is_already_added=is_added,
                on_view=self._on_add_from_search,
                on_report=self._on_report,
            ))

    def _on_add_from_search(self, url: str) -> None:
        from ...controllers.registry.resolver import parse_github_url
        parsed = parse_github_url(url)
        if parsed:
            owner, repo = parsed
            if self._ctrl.is_blacklisted(owner, repo):
                self._set_add_status("This repository is on the block list.", (0.9, 0.3, 0.3, 1))
                return
        self._start_view(url, self._on_add_done)

    def _on_share(self) -> None:
        encoded = self._ctrl.export_registries_b64()
        Clipboard.copy(encoded)
        self._show_snackbar("Registry list copied to clipboard.")

    def _on_rate_limit(self, msg: str = "") -> None:
        RateLimitDialog(reset_str=msg, is_search=False).open()

    def _on_search_rate_limit(self, msg: str = "") -> None:
        RateLimitDialog(reset_str=msg, is_search=True).open()

    def _show_import_dialog(self, urls: list) -> None:
        if not urls:
            self._set_add_status("No registries found in share payload.", (0.9, 0.6, 0.1, 1))
            return

        dlg_ref = [None]

        def _add_all(*_):
            dlg_ref[0].dismiss()
            self._url_field.text = ""
            remaining = [len(urls)]

            def _one_done(success, msg):
                remaining[0] -= 1
                if remaining[0] == 0:
                    def _ui(*_):
                        self._refresh_registries()
                        added = len(urls)
                        word = "registry" if added == 1 else "registries"
                        self._show_snackbar(f"Added {added} {word}.")
                        if self._on_registry_changed:
                            self._on_registry_changed()
                    Clock.schedule_once(_ui, 0)

            for url in urls:
                self._ctrl.add_registry(url, self._game_id, on_done=_one_done)

        def _dismiss(*_):
            dlg_ref[0].dismiss()

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
        dlg_ref[0] = dlg
        dlg.open()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _show_snackbar(self, text: str) -> None:
        MDSnackbar(MDSnackbarText(text=text)).open()
