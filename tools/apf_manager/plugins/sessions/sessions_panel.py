"""
SessionsPanel — hub_panel for session backup/restore.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDIconButton, MDRaisedButton
from kivymd.uix.dialog import MDDialog
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar

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

        self._toolbar = MDTopAppBar(
            title="Sessions",
            elevation=0,
            right_action_items=[
                ["plus", lambda x: self._open_backup_dialog()],
                ["refresh", lambda x: self._refresh()],
            ],
        )
        self.add_widget(self._toolbar)

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
        self._list_layout.clear_widgets()
        svc: Optional["SessionManager"] = self._host.get_service("sessions")
        if not svc or not self._profile:
            self._list_layout.add_widget(MDLabel(
                text="Sessions service not available.",
                halign="center",
                size_hint=(1, None),
                height=dp(48),
            ))
            return

        backups = svc.list_sessions(self._profile.game_id)
        if not backups:
            self._list_layout.add_widget(MDLabel(
                text="No session backups yet.\nPress + to create one.",
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
        name_field = MDTextField(hint_text="Backup name", mode="rectangle")

        def _confirm(*_):
            name = name_field.text.strip() or "backup"
            svc: Optional["SessionManager"] = self._host.get_service("sessions")
            if svc:
                result = svc.backup(name, self._profile.game_id if self._profile else None)
                if result:
                    self._host.log(f"Session backed up: {result.display_name}")
                else:
                    self._host.log("Backup failed — session_state.json not found.")
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
            title="Backup Session",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancel", on_release=_cancel),
                MDRaisedButton(text="Backup", on_release=_confirm),
            ],
        )
        self._backup_dialog.open()

    # -----------------------------------------------------------------------
    # Rename dialog
    # -----------------------------------------------------------------------

    def _open_rename_dialog(self, backup: "SessionBackup", svc: "SessionManager") -> None:
        name_field = MDTextField(
            hint_text="New name",
            text=backup.name,
            mode="rectangle",
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
            title="Rename Backup",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="Cancel", on_release=_cancel),
                MDRaisedButton(text="Rename", on_release=_confirm),
            ],
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
