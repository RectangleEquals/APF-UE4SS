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
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivymd.uix.textfield import MDTextField

if TYPE_CHECKING:
    from ....services.registry_service import RegistryService


class RegistriesTab(MDBoxLayout):
    """Tab 1 — Registries."""

    def __init__(self, host, on_registry_changed=None, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._on_registry_changed = on_registry_changed
        self._url_field: Optional[MDTextField] = None
        self._registries_list: Optional[MDBoxLayout] = None
        self._search_results: Optional[MDBoxLayout] = None
        self._ue4ss_card: Optional[MDBoxLayout] = None
        self._ue4ss_status_icon: Optional[MDIcon] = None
        self._ue4ss_status_lbl: Optional[MDLabel] = None
        self._add_status: Optional[MDLabel] = None
        self._share_btn: Optional[MDButton] = None
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

        # Tab purpose description
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
            MDButtonText(text="View"),
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
        status_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(24),
            spacing=dp(6),
        )
        self._ue4ss_status_icon = MDIcon(
            icon="loading",
            size_hint=(None, 1),
            width=dp(20),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        self._ue4ss_status_lbl = MDLabel(
            text="Checking…",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        )
        status_row.add_widget(self._ue4ss_status_icon)
        status_row.add_widget(self._ue4ss_status_lbl)
        card.add_widget(status_row)
        return card

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def refresh(self, game_id: str, ue4ss_detected: bool) -> None:
        self._game_id = game_id
        if self._search_results is not None:
            self._search_results.clear_widgets()
        self._refresh_ue4ss_card(ue4ss_detected)
        self._refresh_registries()

    def _refresh_ue4ss_card(self, ue4ss_detected: bool) -> None:
        if not ue4ss_detected:
            self._ue4ss_status_icon.icon = "alert"
            self._ue4ss_status_icon.text_color = (0.9, 0.6, 0.1, 1)
            self._ue4ss_status_lbl.text = "UE4SS not detected"
            self._ue4ss_status_lbl.text_color = (0.9, 0.6, 0.1, 1)
            # Remove any previously added update row
            self._remove_ue4ss_update_row()
            return

        updates_svc = self._host.get_service("updates") if self._host.has_service("updates") else None
        ue4ss_info = updates_svc.get_update_info("ue4ss") if updates_svc else None

        current_ver = getattr(ue4ss_info, "current", "unknown") if ue4ss_info else "unknown"
        if current_ver == "unknown":
            status_text = "UE4SS detected (version unknown)"
        else:
            status_text = f"UE4SS detected  v{current_ver}"

        self._ue4ss_status_icon.icon = "check-circle"
        self._ue4ss_status_icon.text_color = (0.3, 0.8, 0.4, 1)
        self._ue4ss_status_lbl.text = status_text
        self._ue4ss_status_lbl.text_color = (0.3, 0.8, 0.4, 1)

        # Add/refresh update notice if an update is available
        self._remove_ue4ss_update_row()
        if ue4ss_info and ue4ss_info.is_update_available and ue4ss_info.latest_stable:
            update_row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(24),
                spacing=dp(6),
            )
            latest_tag = ue4ss_info.latest_stable.tag_name
            update_row.add_widget(MDIcon(
                icon="arrow-up-circle",
                size_hint=(None, 1), width=dp(20),
                theme_text_color="Custom", text_color=(0.25, 0.55, 1.0, 1),
            ))
            update_row.add_widget(MDLabel(
                text=f"Update available: v{latest_tag}",
                font_style="Label", role="small", size_hint=(1, 1),
                theme_text_color="Custom", text_color=(0.25, 0.55, 1.0, 1),
            ))
            update_row._is_ue4ss_update_row = True
            if self._ue4ss_card:
                self._ue4ss_card.add_widget(update_row)

    def _remove_ue4ss_update_row(self) -> None:
        if not self._ue4ss_card:
            return
        to_remove = [w for w in self._ue4ss_card.children
                     if getattr(w, "_is_ue4ss_update_row", False)]
        for w in to_remove:
            self._ue4ss_card.remove_widget(w)

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

        entries = svc.get_user_registries(self._game_id)
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
            row.add_widget(MDIconButton(
                icon="eye",
                theme_icon_color="Custom",
                icon_color=(0.5, 0.75, 1.0, 1),
                on_release=lambda *_, e=entry: self._on_view(e),
            ))
            row.add_widget(MDIconButton(
                icon="flag",
                theme_icon_color="Custom",
                icon_color=(0.9, 0.2, 0.2, 1),
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

        # Blacklist check — never open viewer for blacklisted repos
        from ....utils.registry.resolver import parse_github_url
        parsed = parse_github_url(url)
        if parsed:
            owner, repo = parsed
            resolver_svc = svc._get_resolver() if hasattr(svc, "_get_resolver") else None
            if resolver_svc and resolver_svc.is_blacklisted(owner, repo):
                self._set_add_status("This repository is on the block list.", (0.9, 0.3, 0.3, 1))
                return

        self._set_add_status("Loading…", (0.7, 0.7, 0.7, 1))
        svc.add_registry_with_viewer(url, self._game_id, on_done=self._on_add_done)

    def _on_add_done(self, success: bool, msg: str) -> None:
        color = (0.3, 0.8, 0.4, 1) if success else (0.9, 0.3, 0.3, 1)
        self._set_add_status(msg, color)
        if success:
            self._url_field.text = ""
            self._refresh_registries()
            if self._on_registry_changed:
                self._on_registry_changed()

    def _set_add_status(self, text: str, color) -> None:
        if self._add_status:
            self._add_status.text = text
            self._add_status.text_color = color

    def _on_view(self, entry) -> None:
        """Open the registry viewer for an already-added registry (re-uses cached data)."""
        svc = self._registry_svc()
        if not svc:
            return
        self._set_add_status("Opening viewer…", (0.7, 0.7, 0.7, 1))
        svc.add_registry_with_viewer(
            entry.url, self._game_id,
            on_done=lambda ok, msg: self._set_add_status(
                "" if ok else msg, (0.9, 0.3, 0.3, 1)
            ),
        )

    def _on_remove(self, entry) -> None:
        svc = self._registry_svc()
        if svc:
            svc.remove_registry(entry.url)
        self._refresh_registries()
        self._show_snackbar("Registry removed.")
        if self._on_registry_changed:
            self._on_registry_changed()

    def _on_refresh_one(self, entry) -> None:
        svc = self._registry_svc()
        if not svc:
            return
        self._set_add_status("Refreshing…", (0.7, 0.7, 0.7, 1))

        def _on_refresh_done():
            self._set_add_status("", (0.7, 0.7, 0.7, 1))
            self._refresh_registries()
            self._show_snackbar("Registries refreshed.")
            if self._on_registry_changed:
                self._on_registry_changed()

        svc.refresh_all(on_done=_on_refresh_done)

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

        svc = self._registry_svc()

        # Sort results by freshness + stars score (descending) before display.
        def _search_score(r: dict) -> int:
            days = r.get("last_push_days", 999)
            stars = r.get("stars", 0)
            freshness = 3 if days <= 30 else (2 if days <= 90 else 0)
            import math
            star_pts = min(5, int(math.log10(stars + 1) * 5)) if stars >= 0 else 0
            return freshness + star_pts
        results = sorted(results, key=_search_score, reverse=True)

        self._search_results.add_widget(MDLabel(
            text=f"Found {len(results)} public registry repo(s):",
            font_style="Label",
            size_hint_y=None,
            height=dp(28),
        ))
        for r in results:
            owner, repo = r["owner"], r["repo"]
            is_bl = svc.is_blacklisted(owner, repo) if svc else False
            if is_bl:
                self._host.log(
                    f"[registry] [WARN] Search result {owner}/{repo} is blacklisted — Add disabled"
                )

            card = MDBoxLayout(
                orientation="vertical",
                adaptive_height=True,
                spacing=0,
            )

            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height=dp(40),
                spacing=dp(8),
            )
            info_box = MDBoxLayout(
                orientation="horizontal",
                adaptive_height=True,
                spacing=dp(4),
                size_hint_x=1,
            )
            info_box.add_widget(MDLabel(
                text=f"{owner}/{repo}",
                size_hint_x=1,
                adaptive_height=True,
            ))

            # Freshness dot
            days = r.get("last_push_days", 999)
            if days <= 30:
                dot_color = (0.3, 0.8, 0.4, 1)    # green
            elif days <= 90:
                dot_color = (0.9, 0.7, 0.2, 1)    # yellow
            else:
                dot_color = (0.5, 0.5, 0.5, 1)    # grey
            info_box.add_widget(MDIcon(
                icon="circle-small",
                size_hint=(None, None),
                size=(dp(20), dp(20)),
                theme_icon_color="Custom",
                icon_color=dot_color,
                pos_hint={"center_y": 0.5},
            ))

            # Star count
            star_box = MDBoxLayout(
                orientation="horizontal",
                adaptive_height=True,
                size_hint_x=None,
                width=dp(60),
                spacing=dp(2),
            )
            star_box.add_widget(MDIcon(
                icon="star",
                size_hint=(None, None),
                size=(dp(16), dp(16)),
                theme_icon_color="Custom",
                icon_color=(1, 0.84, 0, 1),
                pos_hint={"center_y": 0.5},
            ))
            star_box.add_widget(MDLabel(
                text=str(r["stars"]),
                size_hint_x=None,
                width=dp(36),
                adaptive_height=True,
            ))
            info_box.add_widget(star_box)
            row.add_widget(info_box)
            row.add_widget(MDIconButton(
                icon="flag",
                theme_icon_color="Custom",
                icon_color=(0.9, 0.2, 0.2, 1),
                pos_hint={"center_y": 0.5},
                on_release=lambda *_, url=r["html_url"]: self._on_report(url),
            ))
            row.add_widget(MDButton(
                MDButtonText(text="View"),
                style="filled",
                size_hint=(None, None),
                size=(dp(64), dp(32)),
                pos_hint={"center_y": 0.5},
                disabled=is_bl,
                on_release=lambda *_, url=r["html_url"]: self._on_add_from_search(url),
            ))
            card.add_widget(row)

            if is_bl:
                warn_row = MDBoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(22),
                    spacing=dp(4),
                    padding=[dp(4), 0],
                )
                warn_row.add_widget(MDIcon(
                    icon="block-helper",
                    size_hint=(None, None),
                    size=(dp(16), dp(16)),
                    theme_icon_color="Custom",
                    icon_color=(0.9, 0.3, 0.3, 1),
                    pos_hint={"center_y": 0.5},
                ))
                warn_row.add_widget(MDLabel(
                    text="On block list.",
                    size_hint_y=None,
                    height=dp(22),
                    theme_text_color="Custom",
                    text_color=(0.9, 0.3, 0.3, 1),
                    font_style="Body",
                    role="small",
                ))
                card.add_widget(warn_row)

            self._search_results.add_widget(card)

    def _on_add_from_search(self, url: str) -> None:
        svc = self._registry_svc()
        if not svc:
            return
        # Blacklist check — never open viewer for blacklisted repos
        from ....utils.registry.resolver import parse_github_url
        parsed = parse_github_url(url)
        if parsed:
            owner, repo = parsed
            resolver_svc = svc._get_resolver() if hasattr(svc, "_get_resolver") else None
            if resolver_svc and resolver_svc.is_blacklisted(owner, repo):
                self._set_add_status("This repository is on the block list.", (0.9, 0.3, 0.3, 1))
                return
        self._set_add_status("Loading…", (0.7, 0.7, 0.7, 1))
        svc.add_registry_with_viewer(url, self._game_id, on_done=self._on_add_done)

    def _on_share(self) -> None:
        svc = self._registry_svc()
        if not svc:
            return
        encoded = svc.export_registries_b64()
        Clipboard.copy(encoded)
        self._show_snackbar("Registry list copied to clipboard.")

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
                svc.add_registry(url, on_done=_one_done)

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

    def _show_snackbar(self, text: str) -> None:
        MDSnackbar(MDSnackbarText(text=text)).open()
