"""
SessionsPanel — hub_panel for session backup/restore.

Layout:
    [Toolbar: Sessions | Refresh]
    [Deployed Session card]
        Path: .../APFrameworkMod/output/session_state.json
        Modified: YYYY-MM-DD HH:MM   Size: N KB     [Backup Now]
        — or —
        No deployed session found.
        Path: ... (greyed)
    [Backups section header]
    [Scrollable backup list]
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogContentContainer,
    MDDialogButtonContainer,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from ...gui.widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from .session_manager import SessionBackup, SessionManager


class SessionsPanel(PluginPanel):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._backup_dialog: Optional[MDDialog] = None
        self._rename_dialog: Optional[MDDialog] = None
        self._build_ui()

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._profile = game_profile
        svc: Optional["SessionManager"] = self._host.get_service("sessions")
        if svc:
            svc.on_game_changed(game_profile, self._host.get_detection())
        self._refresh()

    def on_deactivate(self) -> None:
        pass

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.orientation = "vertical"

        toolbar = MDBoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(56),
            md_bg_color=(0.15, 0.2, 0.25, 1), padding=(dp(8), 0), spacing=dp(4),
        )
        toolbar.add_widget(MDLabel(
            text="Sessions", font_style="Title", role="large",
            size_hint_x=1, halign="left",
        ))
        toolbar.add_widget(MDIconButton(
            icon="refresh", on_release=lambda *_: self._refresh(),
        ))
        self._toolbar = toolbar
        self.add_widget(toolbar)

        # Deployed session card (fixed, non-scrolling)
        self._deployed_card = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            adaptive_height=True,
            md_bg_color=(0.12, 0.16, 0.2, 1),
            padding=[dp(16), dp(8)],
            spacing=dp(4),
        )
        self.add_widget(self._deployed_card)

        # Backups section header
        backups_header = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(36),
            padding=[dp(16), 0],
            md_bg_color=(0.1, 0.1, 0.1, 1),
        )
        backups_header.add_widget(MDLabel(
            text="Backups",
            font_style="Title",
            role="medium",
            size_hint_x=1,
            halign="left",
        ))
        self._add_backup_btn = MDButton(
            MDButtonText(text="+ New Backup"),
            style="text",
            on_release=lambda *_: self._open_backup_dialog(),
        )
        backups_header.add_widget(self._add_backup_btn)
        self.add_widget(backups_header)

        # Scrollable backup list
        self._scroll = ScrollView(size_hint=(1, 1))
        self._list_layout = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(4),
            padding=[dp(16), dp(8)],
        )
        self._scroll.add_widget(self._list_layout)
        self.add_widget(self._scroll)

    def _refresh(self) -> None:
        svc: Optional["SessionManager"] = self._host.get_service("sessions")

        # -- Deployed session section --
        self._deployed_card.clear_widgets()
        self._deployed_card.add_widget(MDLabel(
            text="Deployed Session",
            font_style="Title",
            role="medium",
            size_hint=(1, None),
            height=dp(28),
            halign="left",
        ))

        if not svc or not self._profile:
            self._deployed_card.add_widget(MDLabel(
                text="Sessions service not available.",
                halign="left",
                size_hint=(1, None),
                height=dp(28),
                theme_text_color="Custom",
                text_color=(0.5, 0.5, 0.5, 1),
            ))
        else:
            info = svc.get_deployed_info()
            path_str = str(svc.deployed_path) if svc.deployed_path else "—"
            # Path label (greyed)
            self._deployed_card.add_widget(MDLabel(
                text=f"Path: {path_str}",
                halign="left",
                size_hint=(1, None),
                height=dp(20),
                font_style="Label",
                role="small",
                theme_text_color="Custom",
                text_color=(0.45, 0.45, 0.45, 1),
            ))
            if info:
                dt_str = datetime.fromtimestamp(info["mtime"]).strftime("%Y-%m-%d %H:%M")
                size_kb = info["size"] / 1024
                meta_row = MDBoxLayout(
                    orientation="horizontal",
                    size_hint=(1, None),
                    height=dp(36),
                    spacing=dp(8),
                )
                meta_row.add_widget(MDLabel(
                    text=f"Modified: {dt_str}    Size: {size_kb:.1f} KB",
                    halign="left",
                    size_hint=(1, 1),
                    theme_text_color="Custom",
                    text_color=(0.8, 0.8, 0.8, 1),
                ))
                meta_row.add_widget(MDButton(
                    MDButtonText(text="Backup Now"),
                    style="tonal",
                    size_hint=(None, 1),
                    on_release=lambda *_: self._open_backup_dialog(),
                ))
                self._deployed_card.add_widget(meta_row)
            else:
                self._deployed_card.add_widget(MDLabel(
                    text="No deployed session found.",
                    halign="left",
                    size_hint=(1, None),
                    height=dp(28),
                    theme_text_color="Custom",
                    text_color=(0.55, 0.55, 0.55, 1),
                ))

        # -- Backups list --
        self._list_layout.clear_widgets()
        if not svc or not self._profile:
            return

        backups = svc.list_sessions(self._profile.game_id)
        if not backups:
            self._list_layout.add_widget(MDLabel(
                text="No session backups yet.\nPress '+ New Backup' to create one.",
                halign="center",
                size_hint=(1, None),
                height=dp(80),
            ))
            return

        for backup in backups:
            self._list_layout.add_widget(self._make_row(backup, svc))

    def _make_row(self, backup: "SessionBackup", svc: "SessionManager") -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(52),
            spacing=dp(4),
            padding=[dp(4), dp(4)],
            md_bg_color=(0.14, 0.14, 0.14, 1),
        )
        row.add_widget(MDLabel(
            text=backup.display_name,
            size_hint=(1, 1),
            halign="left",
            valign="middle",
        ))
        row.add_widget(MDIconButton(
            icon="restore",
            size_hint=(None, 1),
            width=dp(40),
            on_release=lambda *_, b=backup: self._on_restore(b, svc),
        ))
        row.add_widget(MDIconButton(
            icon="pencil",
            size_hint=(None, 1),
            width=dp(40),
            on_release=lambda *_, b=backup: self._open_rename_dialog(b, svc),
        ))
        row.add_widget(MDIconButton(
            icon="delete",
            size_hint=(None, 1),
            width=dp(40),
            on_release=lambda *_, b=backup: self._on_delete(b, svc),
        ))
        return row

    # -----------------------------------------------------------------------
    # Backup dialog
    # -----------------------------------------------------------------------

    def _open_backup_dialog(self) -> None:
        name_field = MDTextField(hint_text="Backup name", mode="outlined")

        def _confirm(*_):
            name = name_field.text.strip() or "backup"
            svc: Optional["SessionManager"] = self._host.get_service("sessions")
            if svc:
                result = svc.backup(name, self._profile.game_id if self._profile else None)
                if result:
                    self._host.log(f"Session backed up: {result.display_name}")
                else:
                    self._host.log("Backup failed — deployed session file not found.")
            if self._backup_dialog:
                self._backup_dialog.dismiss()
            self._refresh()

        def _cancel(*_):
            if self._backup_dialog:
                self._backup_dialog.dismiss()

        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(80),
            padding=[dp(4), dp(8)],
        )
        content.add_widget(name_field)

        self._backup_dialog = MDDialog(
            MDDialogHeadlineText(text="Backup Session"),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text="Backup"), style="filled", on_release=_confirm),
            ),
        )
        self._backup_dialog.open()

    # -----------------------------------------------------------------------
    # Rename dialog
    # -----------------------------------------------------------------------

    def _open_rename_dialog(self, backup: "SessionBackup", svc: "SessionManager") -> None:
        name_field = MDTextField(
            hint_text="New name",
            text=backup.name,
            mode="outlined",
        )

        def _confirm(*_):
            new_name = name_field.text.strip()
            if new_name:
                svc.rename(backup, new_name)
                self._refresh()
            if self._rename_dialog:
                self._rename_dialog.dismiss()

        def _cancel(*_):
            if self._rename_dialog:
                self._rename_dialog.dismiss()

        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(80),
            padding=[dp(4), dp(8)],
        )
        content.add_widget(name_field)

        self._rename_dialog = MDDialog(
            MDDialogHeadlineText(text="Rename Backup"),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text="Rename"), style="filled", on_release=_confirm),
            ),
        )
        self._rename_dialog.open()

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_restore(self, backup: "SessionBackup", svc: "SessionManager") -> None:
        if svc.restore(backup):
            self._host.log(f"Session restored: {backup.display_name}")
        else:
            self._host.log("Restore failed — check game context.")

    def _on_delete(self, backup: "SessionBackup", svc: "SessionManager") -> None:
        svc.delete(backup)
        self._host.log(f"Deleted: {backup.display_name}")
        self._refresh()
