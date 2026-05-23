"""
SessionsPanel — hub_panel for session backup/restore.

Three-state dependency guard:
    State 1 (no UE4SS):         Full-screen guard — nothing usable.
    State 2 (UE4SS, no fw mod): Session list visible (read-only); backup/restore
                                 individually blocked with inline explanation.
    State 3 (both present):     Full functionality.

Subscribes to both "detection" and "install" state changes and live-swaps
the body widget on every transition.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogContentContainer,
    MDDialogButtonContainer,
)
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.textfield import MDTextField

from ....core.views.widgets.plugin_panel import PluginPanel
from ..controllers.controller import SessionsController

if TYPE_CHECKING:
    from ....core.models.config import GameProfile
    from ..models.session import SessionBackup


class SessionsPanel(PluginPanel):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self._ctrl = SessionsController(host)
        self._profile: Optional["GameProfile"] = None
        self._backup_dialog: Optional[MDDialog] = None
        self._rename_dialog: Optional[MDDialog] = None
        self._subscribed: bool = False
        self._build_chrome()

    # -----------------------------------------------------------------------
    # Chrome (toolbar + body container — built once, never rebuilt)
    # -----------------------------------------------------------------------

    def _build_chrome(self) -> None:
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
            icon="refresh", on_release=lambda *_: self._refresh_view(),
        ))
        self.add_widget(toolbar)

        self._body = MDBoxLayout(orientation="vertical", size_hint=(1, 1))
        self.add_widget(self._body)

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._profile = game_profile
        self._ctrl.activate(game_profile)
        if not self._subscribed:
            self._host.subscribe_state_change("detection", self._on_state_changed)
            self._host.subscribe_state_change("install", self._on_state_changed)
            self._subscribed = True
        Clock.schedule_once(lambda dt: self._refresh_view(), 0)

    def on_deactivate(self) -> None:
        pass

    def _on_state_changed(self) -> None:
        """Fires on both 'detection' and 'install' changes — re-queries and rebuilds."""
        if self._profile:
            self._ctrl.activate(self._profile)
        Clock.schedule_once(lambda dt: self._refresh_view(), 0)

    # -----------------------------------------------------------------------
    # State-driven view switching
    # -----------------------------------------------------------------------

    def _refresh_view(self) -> None:
        if not self._profile:
            return
        dep = self._ctrl.get_dependency_state()
        self._body.clear_widgets()
        if not dep["ue4ss_ok"]:
            self._body.add_widget(self._build_guard_view(dep))
        elif not dep["fw_installed"]:
            self._body.add_widget(
                self._build_content_view(allow_backup=False, allow_restore=False)
            )
        else:
            self._body.add_widget(
                self._build_content_view(allow_backup=True, allow_restore=True)
            )

    # -----------------------------------------------------------------------
    # Guard view (State 1: no UE4SS — full-screen)
    # -----------------------------------------------------------------------

    def _build_guard_view(self, dep: dict) -> MDBoxLayout:
        ue4ss_ok = dep["ue4ss_ok"]
        fw_installed = dep["fw_installed"]

        guard = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, 1),
            padding=[dp(40), dp(48), dp(40), dp(48)],
            spacing=dp(20),
        )

        # Large alert icon
        icon_row = MDBoxLayout(
            orientation="horizontal", size_hint=(1, None), height=dp(72),
        )
        icon_row.add_widget(Widget(size_hint_x=1))
        icon_row.add_widget(MDIcon(
            icon="alert-circle-outline",
            font_size=dp(60),
            size_hint=(None, None), size=(dp(72), dp(72)),
            pos_hint={"center_y": 0.5},
            theme_icon_color="Custom",
            icon_color=(0.85, 0.55, 0.1, 1),
        ))
        icon_row.add_widget(Widget(size_hint_x=1))
        guard.add_widget(icon_row)

        # Title
        guard.add_widget(MDLabel(
            text="Sessions Unavailable",
            font_style="Title", role="large",
            size_hint=(1, None), height=dp(40),
            halign="center",
        ))

        # Explanation
        guard.add_widget(MDLabel(
            text=(
                "Session backup and restore require UE4SS to be installed.\n"
                "Without UE4SS the mod directory is inaccessible and session\n"
                "files cannot be read or written."
            ),
            size_hint=(1, None), adaptive_height=True,
            halign="center",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
        ))

        # Live status indicator rows
        status_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None), adaptive_height=True,
            spacing=dp(8), padding=[dp(24), 0],
        )
        for req_label, ok in [("UE4SS", ue4ss_ok), ("AP Framework Mod", fw_installed)]:
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint=(1, None), height=dp(32),
                spacing=dp(10),
            )
            row.add_widget(Widget(size_hint_x=1))
            icon_color = (0.25, 0.8, 0.35, 1) if ok else (0.6, 0.6, 0.6, 1)
            row.add_widget(MDIcon(
                icon="check-circle-outline" if ok else "close-circle-outline",
                font_size=dp(18),
                size_hint=(None, 1), width=dp(22),
                theme_icon_color="Custom", icon_color=icon_color,
            ))
            status_color = (0.25, 0.8, 0.35, 1) if ok else (0.6, 0.6, 0.6, 1)
            row.add_widget(MDLabel(
                text=f"{req_label}  {'— installed' if ok else '— not installed'}",
                font_style="Body",
                size_hint=(None, 1), width=dp(280),
                halign="left", valign="middle",
                theme_text_color="Custom", text_color=status_color,
            ))
            row.add_widget(Widget(size_hint_x=1))
            status_box.add_widget(row)
        guard.add_widget(status_box)

        # Install instructions for missing components
        instr_box = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None), adaptive_height=True,
            spacing=dp(4), padding=[dp(24), 0],
        )
        instr_box.add_widget(MDLabel(
            text="To resolve:",
            font_style="Label", role="medium",
            size_hint=(1, None), height=dp(22),
            halign="center",
            theme_text_color="Secondary",
        ))
        if not ue4ss_ok:
            instr_box.add_widget(MDLabel(
                text="→  UE4SS: install via the Content hub, Other section",
                font_style="Body", role="small",
                size_hint=(1, None), height=dp(24),
                halign="center",
                theme_text_color="Custom",
                text_color=(0.85, 0.85, 0.25, 1),
            ))
        if not fw_installed:
            instr_box.add_widget(MDLabel(
                text="→  AP Framework Mod: install via the Content hub, Mods section",
                font_style="Body", role="small",
                size_hint=(1, None), height=dp(24),
                halign="center",
                theme_text_color="Custom",
                text_color=(0.85, 0.85, 0.25, 1),
            ))
        guard.add_widget(instr_box)

        # Spacer to push content to vertical centre
        guard.add_widget(Widget(size_hint_y=1))
        return guard

    # -----------------------------------------------------------------------
    # Content view (States 2 and 3)
    # -----------------------------------------------------------------------

    def _build_content_view(self, *, allow_backup: bool, allow_restore: bool) -> MDBoxLayout:
        container = MDBoxLayout(orientation="vertical", size_hint=(1, 1))

        # Read-only banner (State 2 only — UE4SS present, framework mod absent)
        if not allow_backup:
            banner = MDBoxLayout(
                orientation="horizontal",
                size_hint=(1, None), height=dp(48),
                md_bg_color=(0.3, 0.2, 0.05, 1),
                padding=[dp(12), 0], spacing=dp(8),
            )
            banner.add_widget(MDIcon(
                icon="information-outline",
                font_size=dp(20),
                size_hint=(None, 1), width=dp(28),
                theme_icon_color="Custom",
                icon_color=(0.95, 0.7, 0.2, 1),
            ))
            banner.add_widget(MDLabel(
                text=(
                    "AP Framework Mod not installed — session history is read-only. "
                    "Install the framework mod to create or restore backups."
                ),
                size_hint=(1, 1),
                halign="left", valign="middle",
                font_style="Body", role="small",
                theme_text_color="Custom",
                text_color=(0.9, 0.75, 0.4, 1),
            ))
            container.add_widget(banner)

        # Deployed session card
        container.add_widget(
            self._build_deployed_card(allow_backup=allow_backup)
        )

        # Backups section header
        backups_header = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None), height=dp(36),
            padding=[dp(16), 0],
            md_bg_color=(0.1, 0.1, 0.1, 1),
        )
        backups_header.add_widget(MDLabel(
            text="Backups",
            font_style="Title", role="medium",
            size_hint_x=1, halign="left",
        ))
        if allow_backup:
            backups_header.add_widget(MDButton(
                MDButtonText(text="+ New Backup"),
                style="text",
                on_release=lambda *_: self._open_backup_dialog(),
            ))
        container.add_widget(backups_header)

        # Scrollable backup list
        scroll = ScrollView(size_hint=(1, 1))
        list_layout = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(4),
            padding=[dp(16), dp(8)],
        )
        scroll.add_widget(list_layout)
        container.add_widget(scroll)

        if self._ctrl.has_service() and self._profile:
            backups = self._ctrl.get_sessions(self._profile.game_id)
            if backups:
                for backup in backups:
                    list_layout.add_widget(
                        self._make_row(backup, allow_restore=allow_restore)
                    )
            else:
                empty_text = (
                    "No session backups yet.\nPress '+ New Backup' to create one."
                    if allow_backup else
                    "No session backups yet."
                )
                list_layout.add_widget(MDLabel(
                    text=empty_text,
                    halign="center",
                    size_hint=(1, None), height=dp(80),
                    theme_text_color="Custom",
                    text_color=(0.5, 0.5, 0.5, 1),
                ))

        return container

    def _build_deployed_card(self, *, allow_backup: bool) -> MDBoxLayout:
        card = MDBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            adaptive_height=True,
            md_bg_color=(0.12, 0.16, 0.2, 1),
            padding=[dp(16), dp(8)],
            spacing=dp(4),
        )
        card.add_widget(MDLabel(
            text="Deployed Session",
            font_style="Title", role="medium",
            size_hint=(1, None), height=dp(28),
            halign="left",
        ))

        if not self._ctrl.has_service() or not self._profile:
            card.add_widget(MDLabel(
                text="Sessions service not available.",
                halign="left",
                size_hint=(1, None), height=dp(28),
                theme_text_color="Custom",
                text_color=(0.5, 0.5, 0.5, 1),
            ))
            return card

        path_str = self._ctrl.get_deployed_path_str()
        card.add_widget(MDLabel(
            text=f"Path: {path_str}",
            halign="left",
            size_hint=(1, None), height=dp(20),
            font_style="Label", role="small",
            theme_text_color="Custom",
            text_color=(0.45, 0.45, 0.45, 1),
        ))

        info = self._ctrl.get_deployed_info()
        if info:
            dt_str = datetime.fromtimestamp(info["mtime"]).strftime("%Y-%m-%d %H:%M")
            size_kb = info["size"] / 1024
            meta_row = MDBoxLayout(
                orientation="horizontal",
                size_hint=(1, None), height=dp(36),
                spacing=dp(8),
            )
            meta_row.add_widget(MDLabel(
                text=f"Modified: {dt_str}    Size: {size_kb:.1f} KB",
                halign="left", size_hint=(1, 1),
                theme_text_color="Custom",
                text_color=(0.8, 0.8, 0.8, 1),
            ))
            if allow_backup:
                meta_row.add_widget(MDButton(
                    MDButtonText(text="Backup Now"),
                    style="tonal",
                    size_hint=(None, 1),
                    on_release=lambda *_: self._open_backup_dialog(),
                ))
            else:
                meta_row.add_widget(MDLabel(
                    text="Requires AP Framework Mod to backup",
                    halign="right",
                    size_hint=(None, 1), width=dp(240),
                    font_style="Label", role="small",
                    theme_text_color="Custom",
                    text_color=(0.5, 0.5, 0.5, 1),
                ))
            card.add_widget(meta_row)
        else:
            card.add_widget(MDLabel(
                text="No deployed session found.",
                halign="left",
                size_hint=(1, None), height=dp(28),
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            ))

        return card

    def _make_row(self, backup: "SessionBackup", *, allow_restore: bool) -> MDBoxLayout:
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None), height=dp(56),
            spacing=dp(4), padding=[dp(4), dp(4)],
            md_bg_color=(0.14, 0.14, 0.14, 1),
        )
        row.add_widget(MDLabel(
            text=backup.display_name,
            size_hint=(1, 1),
            halign="left", valign="middle",
        ))

        if allow_restore:
            row.add_widget(MDIconButton(
                icon="restore",
                size_hint=(None, 1), width=dp(40),
                on_release=lambda *_, b=backup: self._on_restore(b),
            ))
        else:
            # Disabled restore — icon + explanatory caption stacked vertically
            lock_col = MDBoxLayout(
                orientation="vertical",
                size_hint=(None, 1), width=dp(100),
                spacing=0,
            )
            restore_btn = MDIconButton(icon="restore", size_hint=(1, None), height=dp(36))
            restore_btn.disabled = True
            lock_col.add_widget(restore_btn)
            lock_col.add_widget(MDLabel(
                text="Requires\nframework mod",
                halign="center",
                size_hint=(1, None), height=dp(20),
                font_style="Label", role="small",
                theme_text_color="Custom",
                text_color=(0.5, 0.5, 0.5, 1),
            ))
            row.add_widget(lock_col)

        row.add_widget(MDIconButton(
            icon="pencil",
            size_hint=(None, 1), width=dp(40),
            on_release=lambda *_, b=backup: self._open_rename_dialog(b),
        ))
        row.add_widget(MDIconButton(
            icon="delete",
            size_hint=(None, 1), width=dp(40),
            on_release=lambda *_, b=backup: self._on_delete(b),
        ))
        return row

    # -----------------------------------------------------------------------
    # Backup dialog
    # -----------------------------------------------------------------------

    def _open_backup_dialog(self) -> None:
        name_field = MDTextField(hint_text="Backup name", mode="outlined")

        def _confirm(*_):
            name = name_field.text.strip() or "backup"
            result = self._ctrl.backup(name, self._profile.game_id if self._profile else "")
            if result:
                self._host.log(f"Session backed up: {result.display_name}")
            else:
                self._host.log("Backup failed — deployed session file not found.")
            if self._backup_dialog:
                self._backup_dialog.dismiss()
            self._refresh_view()

        def _cancel(*_):
            if self._backup_dialog:
                self._backup_dialog.dismiss()

        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None, height=dp(80),
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

    def _open_rename_dialog(self, backup: "SessionBackup") -> None:
        name_field = MDTextField(
            hint_text="New name", text=backup.name, mode="outlined",
        )

        def _confirm(*_):
            new_name = name_field.text.strip()
            if new_name:
                self._ctrl.rename(backup, new_name)
                self._refresh_view()
            if self._rename_dialog:
                self._rename_dialog.dismiss()

        def _cancel(*_):
            if self._rename_dialog:
                self._rename_dialog.dismiss()

        content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None, height=dp(80),
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

    def _on_restore(self, backup: "SessionBackup") -> None:
        if self._ctrl.restore(backup):
            self._host.log(f"Session restored: {backup.display_name}")
        else:
            self._host.log("Restore failed — check game context.")

    def _on_delete(self, backup: "SessionBackup") -> None:
        self._ctrl.delete(backup)
        self._host.log(f"Deleted: {backup.display_name}")
        self._refresh_view()
