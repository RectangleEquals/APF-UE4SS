from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Callable, Optional

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer, MDDialogContentContainer,
)
from kivymd.uix.divider import MDDivider
from kivymd.uix.label import MDLabel

from ...controllers.tabs.account import AccountController
from .....core.views.widgets.tip_icon_button import ImageTextButton

_DISCORD_ICON = (
    Path(__file__).parent.parent.parent.parent.parent / "data" / "Discord_Symbol_White.png"
)


class AccountTab(MDBoxLayout):
    """Account tab — auth state, login/logout, rate limit display."""

    def __init__(
        self,
        ctrl: AccountController,
        on_auth_changed: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            orientation="vertical",
            adaptive_height=True,
            padding=dp(16),
            spacing=dp(8),
            **kwargs,
        )
        self._ctrl = ctrl
        self._on_auth_changed = on_auth_changed

    def rebuild(self) -> None:
        self.clear_widgets()
        if not self._ctrl.is_logged_in:
            self._build_logged_out()
        else:
            self._build_logged_in()

    # -----------------------------------------------------------------------
    # Logged out
    # -----------------------------------------------------------------------

    def _build_logged_out(self) -> None:
        self.add_widget(MDLabel(
            text="Sign in to GitHub to enable contribution tools and developer features.",
            adaptive_height=True,
            theme_text_color="Secondary",
        ))
        login_btn = MDButton(
            MDButtonIcon(icon="github"),
            MDButtonText(text="Sign In with GitHub"),
        )
        login_btn.bind(on_release=lambda *_: self._start_login_flow())
        self.add_widget(login_btn)

    # -----------------------------------------------------------------------
    # Logged in
    # -----------------------------------------------------------------------

    def _build_logged_in(self) -> None:
        perm = self._ctrl.permission
        perm_display = (perm or "?").upper()
        write_tier = self._ctrl.is_write_tier

        row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
        row.add_widget(MDLabel(
            text=f"@{self._ctrl.username}",
            adaptive_height=True,
            size_hint_x=0.5,
        ))
        row.add_widget(MDLabel(
            text=f"[{perm_display}]",
            adaptive_height=True,
            size_hint_x=0.2,
            theme_text_color="Custom",
            text_color=(0.2, 0.8, 0.3, 1) if write_tier else (0.6, 0.6, 0.6, 1),
        ))
        logout_btn = MDButton(
            MDButtonIcon(icon="logout"),
            MDButtonText(text="Sign Out"),
            size_hint_x=None,
        )
        logout_btn.bind(on_release=lambda *_: self._logout())
        row.add_widget(logout_btn)
        self.add_widget(row)

        self.add_widget(MDDivider())
        if not write_tier:
            self.add_widget(MDLabel(
                text=(
                    "Write access lets you create PRs, manage branches, "
                    "trigger CI, and push version tags."
                ),
                adaptive_height=True,
                theme_text_color="Secondary",
                font_style="Body",
            ))
            req_btn = MDButton(
                MDButtonIcon(icon="account-plus"),
                MDButtonText(text="Request Write Access"),
            )
            req_btn.bind(on_release=lambda *_: self._show_request_write_dialog())
            self.add_widget(req_btn)

        self.add_widget(MDDivider())
        self.add_widget(MDLabel(
            text="GitHub API",
            font_style="Label",
            role="medium",
            adaptive_height=True,
            theme_text_color="Secondary",
        ))
        self._build_rate_limit_section()

    def _build_rate_limit_section(self) -> None:
        from .....core.controllers.remote.github_api import _format_reset_time
        rest_info, search_info = self._ctrl.get_rate_limit_info()

        def _rl_row(label: str, info) -> MDBoxLayout:
            row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(8))
            if info:
                remaining, limit, reset_ts = info
                color = (0.9, 0.3, 0.3, 1) if remaining < 10 else (0.3, 0.8, 0.4, 1)
                row.add_widget(MDLabel(
                    text=f"{label}: {remaining} / {limit}",
                    adaptive_height=True, size_hint_x=0.6,
                    theme_text_color="Custom", text_color=color,
                ))
                reset_text = f"Resets at: {_format_reset_time(reset_ts)}" if reset_ts else ""
                row.add_widget(MDLabel(
                    text=reset_text, adaptive_height=True, size_hint_x=0.4,
                    theme_text_color="Secondary",
                ))
            else:
                row.add_widget(MDLabel(
                    text=f"{label}: unknown",
                    adaptive_height=True, theme_text_color="Secondary",
                ))
            return row

        if not rest_info and not search_info:
            self.add_widget(MDLabel(
                text="Rate limit: unknown (no API calls made yet)",
                adaptive_height=True, theme_text_color="Secondary", font_style="Body",
            ))
            return

        self.add_widget(_rl_row("REST (5000/hr)",  rest_info))
        self.add_widget(_rl_row("Search (30/min)", search_info))

    # -----------------------------------------------------------------------
    # Login flow
    # -----------------------------------------------------------------------

    def _start_login_flow(self) -> None:
        code_lbl = MDLabel(text="", adaptive_height=True)
        url_lbl  = MDLabel(text="Connecting to GitHub...", adaptive_height=True, font_style="Body")
        dialog_ref: list = [None]

        def _copy_code(*_):
            text = getattr(code_lbl, "_raw_code", "")
            if text:
                Clipboard.copy(text)

        def _copy_url(*_):
            text = getattr(url_lbl, "_raw_url", "")
            if text:
                Clipboard.copy(text)

        code_row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(4))
        code_row.add_widget(MDLabel(
            text="Device Code:", adaptive_height=True,
            size_hint_x=None, width=dp(120), theme_text_color="Secondary",
        ))
        code_row.add_widget(code_lbl)
        copy_code_btn = MDIconButton(icon="content-copy", size_hint_x=None, width=dp(36))
        copy_code_btn.bind(on_release=_copy_code)
        code_row.add_widget(copy_code_btn)

        url_row = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(4))
        url_row.add_widget(MDLabel(
            text="Verification URL:", adaptive_height=True,
            size_hint_x=None, width=dp(120), theme_text_color="Secondary",
        ))
        url_row.add_widget(url_lbl)
        copy_url_btn = MDIconButton(icon="content-copy", size_hint_x=None, width=dp(36))
        copy_url_btn.bind(on_release=_copy_url)
        url_row.add_widget(copy_url_btn)

        def _on_dismissed(*_):
            dialog_ref[0] = None

        dialog = MDDialog(
            MDDialogHeadlineText(text="Sign In with GitHub"),
            MDDialogSupportingText(
                text=(
                    "Verifies your identity and access level. "
                    "No access to personal repositories is requested."
                ),
            ),
            MDDialogContentContainer(
                code_row, url_row,
                orientation="vertical", spacing=dp(8),
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(
                    MDButtonText(text="Cancel"),
                    on_release=lambda *_: dialog_ref[0] and dialog_ref[0].dismiss(),
                ),
            ),
        )
        dialog.bind(on_dismiss=_on_dismissed)
        dialog_ref[0] = dialog
        dialog.open()

        def _on_code(user_code: str, verification_uri: str) -> None:
            def _update(dt):
                code_lbl._raw_code = user_code
                url_lbl._raw_url   = verification_uri
                code_lbl.text = f"[b]{user_code}[/b]"
                code_lbl.markup = True
                url_lbl.text  = verification_uri
            Clock.schedule_once(_update)

        def _on_complete(success: bool, username_or_error: str) -> None:
            def _update(dt):
                if dialog_ref[0]:
                    dialog_ref[0].dismiss()
                self.rebuild()
                if success:
                    self._ctrl.propagate_token()
                if self._on_auth_changed:
                    self._on_auth_changed()
            Clock.schedule_once(_update)

        self._ctrl.start_login(on_code=_on_code, on_complete=_on_complete)

    # -----------------------------------------------------------------------
    # Logout
    # -----------------------------------------------------------------------

    def _logout(self) -> None:
        self._ctrl.logout()
        self._ctrl.propagate_token_clear()
        self.rebuild()
        if self._on_auth_changed:
            self._on_auth_changed()

    # -----------------------------------------------------------------------
    # Request write dialog
    # -----------------------------------------------------------------------

    def _show_request_write_dialog(self) -> None:
        discord_url = "https://discord.gg/xhcVRhnjK"
        dialog_ref: list = [None]

        def _dismiss(*_):
            if dialog_ref[0] is not None:
                d = dialog_ref[0]
                dialog_ref[0] = None
                d.dismiss()

        discord_btn = ImageTextButton(
            source=str(_DISCORD_ICON) if _DISCORD_ICON.exists() else "",
            text="Join Discord",
        )
        discord_btn.bind(on_release=lambda *_: (_dismiss(), webbrowser.open(discord_url)))

        dialog = MDDialog(
            MDDialogHeadlineText(text="Request Write Access"),
            MDDialogSupportingText(
                text=(
                    "To become a collaborator you must:\n"
                    "• Have contributed to the project (merged PR or existing collaborator)\n"
                    "• Contact the team via Discord\n\n"
                    "Join the Discord server to get in touch."
                ),
            ),
            MDDialogButtonContainer(
                Widget(),
                discord_btn,
                MDButton(MDButtonText(text="Close"), style="text", on_release=_dismiss),
            ),
        )
        dialog_ref[0] = dialog
        dialog.open()
