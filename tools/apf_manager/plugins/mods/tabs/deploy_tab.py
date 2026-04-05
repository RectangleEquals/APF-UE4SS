"""
Tab 5 — Deploy

Exact DeployPanel content minus the Validate button and column.
Calls DeployService unchanged.
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
from kivymd.uix.selectioncontrol import MDSwitch

from ....gui.widgets.tip_icon_button import TipIconButton

if TYPE_CHECKING:
    from ...deploy.deploy_panel import ModRow
    from ...mods.mod_service import ModInfo
    from ....core.config import GameProfile
    from ....core.ue4ss import UE4SSResult


_SCAN_EXCLUDE = {"shared"}


class DeployTab(MDBoxLayout):
    """Tab 5 — Deploy (run install steps, deploy all mods)."""

    def __init__(self, host, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._rows: list = []
        self._show_all: bool = False
        self._build_ui()

    @property
    def _deploy_svc(self):
        return self._host.get_service("deploy")

    @property
    def _mods_txt(self):
        svc = self._deploy_svc
        return svc.mods_txt if svc else None

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            md_bg_color=(0.12, 0.16, 0.20, 1),
            padding=(dp(8), 0),
            spacing=dp(4),
        )
        toolbar.add_widget(MDLabel(
            text="Deploy",
            font_style="Title",
            role="medium",
            size_hint_x=1,
            halign="left",
        ))
        toolbar.add_widget(MDLabel(
            text="Show All",
            size_hint=(None, 1),
            width=dp(64),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        ))
        self._show_all_switch = MDSwitch(size_hint=(None, None), pos_hint={"center_y": 0.5})
        self._show_all_switch.active = False
        self._show_all_switch.bind(active=lambda inst, val: self._on_show_all(val))
        toolbar.add_widget(self._show_all_switch)
        toolbar.add_widget(TipIconButton(
            icon="refresh",
            tooltip_text="Rescan mods",
            on_release=lambda *_: self._on_rescan(),
        ))
        toolbar.add_widget(TipIconButton(
            icon="rocket-launch",
            tooltip_text="Deploy all mods",
            on_release=lambda *_: self._on_deploy_all(),
        ))
        self.add_widget(toolbar)

        # Scrollable mod list
        self._scroll = ScrollView(size_hint=(1, 1))
        self._list_layout = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(2),
            padding=[dp(8), dp(4)],
        )
        self._scroll.add_widget(self._list_layout)
        self.add_widget(self._scroll)

    # -----------------------------------------------------------------------
    # Refresh
    # -----------------------------------------------------------------------

    def refresh(self, profile: Optional["GameProfile"], detection) -> None:
        self._profile = profile
        self._detection = detection
        self._do_refresh()

    def _do_refresh(self) -> None:
        from ....plugins.deploy.deploy_panel import ModRow, _SCAN_EXCLUDE as _DEP_EXCL
        from ....plugins.deploy.validator import Validator

        self._list_layout.clear_widgets()
        self._rows = []

        mods_svc = self._host.get_service("mods")
        mods = mods_svc.scan() if mods_svc else []
        mods = [m for m in mods if m.folder_name not in _DEP_EXCL]
        if not self._show_all:
            mods = [m for m in mods if m.is_ap_mod]

        if not mods:
            self._list_layout.add_widget(MDLabel(
                text="No mods found.",
                halign="center",
                size_hint=(1, None),
                height=dp(60),
            ))
            return

        if self._mods_txt:
            order = self._mods_txt.get_order()
            order_idx = {name: i for i, name in enumerate(order)}
            mods.sort(key=lambda m: order_idx.get(m.folder_name, len(order)))

        validator = None
        if self._detection and self._mods_txt:
            validator = Validator(self._detection, self._mods_txt, mods)

        for mod in mods:
            status = "unknown"
            if validator:
                results = validator.validate_mod(mod)
                status = Validator.worst_status(results)

            enabled = True
            if self._mods_txt:
                if self._mods_txt.contains(mod.folder_name):
                    enabled = self._mods_txt.is_enabled(mod.folder_name)

            row = ModRow(
                mod=mod,
                status=status,
                enabled=enabled,
                on_toggle=self._on_toggle,
                on_move_up=lambda m: None,   # No reorder in Deploy tab
                on_move_down=lambda m: None,
                on_manual_step=self._on_manual_step,
            )
            self._rows.append(row)
            self._list_layout.add_widget(row)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def _on_show_all(self, val: bool) -> None:
        self._show_all = val
        self._do_refresh()

    def _on_rescan(self) -> None:
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            mods_svc.rescan()
        svc = self._deploy_svc
        if svc:
            svc.reload()
        self._do_refresh()

    def _on_deploy_all(self) -> None:
        if not self._profile or not self._detection:
            self._host.log("No game context — cannot deploy.")
            return
        threading.Thread(target=self._deploy_all_bg, daemon=True).start()

    def _deploy_all_bg(self) -> None:
        svc = self._deploy_svc
        if not svc:
            return

        def _log(msg):
            Clock.schedule_once(lambda dt, m=msg: self._host.log(m), 0)

        svc.deploy_all(log_fn=_log)
        Clock.schedule_once(lambda dt: self._do_refresh(), 0)
        Clock.schedule_once(lambda dt: self._host.log("Deploy complete."), 0)

    def _on_toggle(self, mod, enabled: bool) -> None:
        svc = self._deploy_svc
        if svc:
            svc.set_enabled(mod.folder_name, enabled)

    def _on_manual_step(self, mod, step) -> None:
        # Delegate to the same logic as DeployPanel
        title = step.title or step.caption or "Manual Step"
        if step.type == "file":
            resolved = None
            if self._profile and self._profile.source_project:
                from pathlib import Path
                p = Path(self._profile.source_project) / step.content
                if p.exists():
                    resolved = p
            if resolved and self._host.has_service("docs_viewer"):
                self._host.show_dialog("docs_viewer", path=str(resolved))
                return

        from kivymd.uix.dialog import (
            MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
            MDDialogButtonContainer,
        )

        def _close(*_):
            dlg.dismiss()

        content = step.content or f"Follow the instructions for: {step.caption}"
        dlg = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogSupportingText(text=content[:2000]),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="OK"), style="text", on_release=_close),
            ),
        )
        dlg.open()
