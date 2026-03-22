"""
DeployPanel — hub_panel UI for the deploy plugin.

Layout:
    [Top toolbar: Rescan | Deploy All | Validate | Clean]
    [Mod list: scrollable rows]
        Row: ▲▼ | name + version | status badge | enable toggle | action buttons
    [LogPanel at bottom (shared via host)]

Mod row color coding:
    default  — normal AP mod
    amber    — warning (unmet prefers_after, warns)
    red      — error (missing dep, incompatible)
    grey     — disabled
    dim text — non-AP mod row (not managed by APF)
"""

from __future__ import annotations

import threading
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogContentContainer, MDDialogButtonContainer,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.toolbar import MDTopAppBar

from ...gui.widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.ue4ss import UE4SSResult
    from ..mods.mod_service import ModInfo, ModService
    from .validator import ValidationResult


# ---------------------------------------------------------------------------
# Status badge colours
# ---------------------------------------------------------------------------

_STATUS_COLORS = {
    "ok":      (0.3, 0.7, 0.4, 1),
    "warn":    (0.9, 0.7, 0.1, 1),
    "error":   (0.9, 0.3, 0.3, 1),
    "unknown": (0.5, 0.5, 0.5, 1),
}

_ROW_BG_NORMAL   = (0.14, 0.14, 0.14, 1)
_ROW_BG_WARN     = (0.22, 0.18, 0.08, 1)
_ROW_BG_ERROR    = (0.22, 0.10, 0.10, 1)
_ROW_BG_DISABLED = (0.10, 0.10, 0.10, 1)
_ROW_BG_NONAP    = (0.11, 0.11, 0.11, 1)


# ---------------------------------------------------------------------------
# ModRow widget
# ---------------------------------------------------------------------------

class ModRow(MDBoxLayout):
    def __init__(
        self,
        mod: "ModInfo",
        status: str,
        on_toggle,
        on_move_up,
        on_move_down,
        on_manual_step,
        **kwargs,
    ):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(48),
            padding=[dp(4), dp(4)],
            spacing=dp(4),
            **kwargs,
        )
        self._mod = mod
        self._status = status
        self._build(on_toggle, on_move_up, on_move_down, on_manual_step)
        self._apply_row_color(status, mod)

    def _apply_row_color(self, status: str, mod: "ModInfo") -> None:
        if not mod.is_ap_mod:
            self.md_bg_color = _ROW_BG_NONAP
        elif not self._is_enabled():
            self.md_bg_color = _ROW_BG_DISABLED
        elif status == "error":
            self.md_bg_color = _ROW_BG_ERROR
        elif status == "warn":
            self.md_bg_color = _ROW_BG_WARN
        else:
            self.md_bg_color = _ROW_BG_NORMAL

    def _is_enabled(self) -> bool:
        return getattr(self, "_checkbox", None) and self._checkbox.active

    def _build(self, on_toggle, on_move_up, on_move_down, on_manual_step) -> None:
        mod = self._mod

        # Reorder buttons (only for AP mods)
        if mod.is_ap_mod:
            up_btn = MDIconButton(
                icon="chevron-up",
                size_hint=(None, 1),
                width=dp(32),
                on_release=lambda *_: on_move_up(mod),
            )
            down_btn = MDIconButton(
                icon="chevron-down",
                size_hint=(None, 1),
                width=dp(32),
                on_release=lambda *_: on_move_down(mod),
            )
            self.add_widget(up_btn)
            self.add_widget(down_btn)
        else:
            # Spacer for alignment
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=dp(64)))

        # Name + version
        name_text = mod.display_name
        if mod.version:
            name_text += f"  v{mod.version}"
        name_lbl = MDLabel(
            text=name_text,
            font_style="Body2",
            size_hint=(1, 1),
            halign="left",
            valign="middle",
            theme_text_color="Custom" if not mod.is_ap_mod else "Primary",
            text_color=(0.5, 0.5, 0.5, 1) if not mod.is_ap_mod else (1, 1, 1, 0.87),
        )
        self.add_widget(name_lbl)

        # Status badge (coloured dot)
        color = _STATUS_COLORS.get(self._status, _STATUS_COLORS["unknown"])
        badge = MDLabel(
            text="●",
            size_hint=(None, 1),
            width=dp(20),
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=color,
        )
        self.add_widget(badge)

        # Enable/disable checkbox (only for AP mods)
        if mod.is_ap_mod:
            cb = MDCheckbox(
                size_hint=(None, 1),
                width=dp(40),
                active=True,
            )
            cb.bind(active=lambda inst, val: on_toggle(mod, val))
            self._checkbox = cb
            self.add_widget(cb)

        # "button" manual step buttons
        for step in mod.manual_steps:
            if step.when == "button" and step.caption:
                btn = MDButton(
                    MDButtonText(text=step.caption),
                    style="text",
                    size_hint=(None, 1),
                    width=dp(80),
                    on_release=lambda *_, s=step: on_manual_step(mod, s),
                )
                self.add_widget(btn)


# ---------------------------------------------------------------------------
# DeployPanel
# ---------------------------------------------------------------------------

class DeployPanel(PluginPanel):
    """
    hub_panel for deploy plugin.
    Receives mods via 'mods' service, renders a list, handles deploy/validate.
    """

    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._detection: Optional["UE4SSResult"] = None
        self._rows: list[ModRow] = []
        self._validation_dialog: Optional[MDDialog] = None
        self._build_ui()

    @property
    def _deploy_svc(self):
        return self._host.get_service("deploy")

    @property
    def _mods_txt(self):
        svc = self._deploy_svc
        return svc.mods_txt if svc else None

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._profile = game_profile
        self._detection = self._host.get_detection()
        self._refresh()

    def on_deactivate(self) -> None:
        pass

    # -----------------------------------------------------------------------
    # Build UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.orientation = "vertical"

        # Toolbar
        self._toolbar = MDTopAppBar(
            title="Mods",
            elevation=0,
            right_action_items=[
                ["refresh", lambda x: self._on_rescan()],
                ["rocket-launch", lambda x: self._on_deploy_all()],
                ["check-circle", lambda x: self._on_validate()],
            ],
        )
        self.add_widget(self._toolbar)

        # Scrollable mod list
        self._scroll = ScrollView(size_hint=(1, 1))
        self._list_layout = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(2),
            padding=[dp(8), dp(8)],
        )
        self._scroll.add_widget(self._list_layout)
        self.add_widget(self._scroll)

    # -----------------------------------------------------------------------
    # Data loading
    # -----------------------------------------------------------------------

    def _get_mods(self) -> list["ModInfo"]:
        svc = self._host.get_service("mods")
        return svc.scan() if svc else []

    def _refresh(self) -> None:
        self._list_layout.clear_widgets()
        self._rows = []

        mods = self._get_mods()
        if not mods:
            self._list_layout.add_widget(MDLabel(
                text="No mods found in this game's Mods directory.",
                halign="center",
                size_hint=(1, None),
                height=dp(60),
            ))
            return

        # Build validator if we have enough context
        validator = self._build_validator(mods)

        for mod in mods:
            if validator:
                results = validator.validate_mod(mod)
                from .validator import Validator
                status = Validator.worst_status(results)
            else:
                status = "unknown"

            # Sync enabled state from mods_txt
            if self._mods_txt:
                enabled = self._mods_txt.is_enabled(mod.folder_name)
            else:
                enabled = True

            row = ModRow(
                mod=mod,
                status=status,
                on_toggle=self._on_toggle,
                on_move_up=self._on_move_up,
                on_move_down=self._on_move_down,
                on_manual_step=self._on_manual_step,
            )
            self._rows.append(row)
            self._list_layout.add_widget(row)

    def _build_validator(self, mods):
        mods_txt = self._mods_txt
        if not self._detection or not mods_txt:
            return None
        from .validator import Validator
        return Validator(self._detection, mods_txt, mods)

    # -----------------------------------------------------------------------
    # Toolbar actions
    # -----------------------------------------------------------------------

    def _on_rescan(self) -> None:
        mods_svc = self._host.get_service("mods")
        if mods_svc:
            mods_svc.rescan()
        deploy_svc = self._deploy_svc
        if deploy_svc:
            deploy_svc.reload()
        self._refresh()
        self._host.log("Mods rescanned.")

    def _on_deploy_all(self) -> None:
        if not self._profile or not self._detection:
            self._host.log("No game context — cannot deploy.")
            return
        threading.Thread(target=self._deploy_all_bg, daemon=True).start()

    def _deploy_all_bg(self) -> None:
        svc = self._deploy_svc
        if not svc:
            Clock.schedule_once(lambda dt: self._host.log("deploy service unavailable."), 0)
            return

        def _log(msg):
            Clock.schedule_once(lambda dt, m=msg: self._host.log(m), 0)

        svc.deploy_all(log_fn=_log)
        Clock.schedule_once(lambda dt: self._refresh(), 0)
        Clock.schedule_once(lambda dt: self._host.log("Deploy complete."), 0)

    def _on_validate(self) -> None:
        mods = self._get_mods()
        if not mods:
            return
        validator = self._build_validator(mods)
        if not validator:
            self._host.log("Cannot validate — no mods.txt available.")
            return

        lines = []
        for mod in mods:
            results = validator.validate_mod(mod)
            for r in results:
                icon = {"ok": "✓", "warn": "⚠", "error": "✗"}.get(r.status, "?")
                lines.append(f"{icon} {mod.display_name}: {r.label}")
                if r.detail:
                    lines.append(f"    {r.detail}")

        body = "\n".join(lines) if lines else "All checks passed."

        def _dismiss(*_):
            if self._validation_dialog:
                self._validation_dialog.dismiss()

        self._validation_dialog = MDDialog(
            MDDialogHeadlineText(text="Validation Results"),
            MDDialogSupportingText(text=body),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Close"), style="text", on_release=_dismiss),
            ),
        )
        self._validation_dialog.open()

    # -----------------------------------------------------------------------
    # Row actions
    # -----------------------------------------------------------------------

    def _on_toggle(self, mod: "ModInfo", enabled: bool) -> None:
        svc = self._deploy_svc
        if svc:
            svc.set_enabled(mod.folder_name, enabled)

    def _on_move_up(self, mod: "ModInfo") -> None:
        svc = self._deploy_svc
        if not svc:
            return
        order = svc.get_load_order()
        idx = next((i for i, n in enumerate(order) if n == mod.folder_name), None)
        if idx is not None and idx > 0:
            order[idx], order[idx - 1] = order[idx - 1], order[idx]
            svc.reorder(order)
            self._refresh()

    def _on_move_down(self, mod: "ModInfo") -> None:
        svc = self._deploy_svc
        if not svc:
            return
        order = svc.get_load_order()
        idx = next((i for i, n in enumerate(order) if n == mod.folder_name), None)
        if idx is not None and idx < len(order) - 1:
            order[idx], order[idx + 1] = order[idx + 1], order[idx]
            svc.reorder(order)
            self._refresh()

    def _on_manual_step(self, mod: "ModInfo", step) -> None:
        content_text = step.content or f"Follow the instructions for: {step.caption}"
        title = step.title or step.caption or "Manual Step"

        # If content is a file path (relative to source_project), try to read it
        if step.type == "file" and self._profile and self._profile.source_project:
            from pathlib import Path
            file_path = Path(self._profile.source_project) / step.content
            if file_path.exists():
                try:
                    content_text = file_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        def _close(*_):
            if hasattr(self, "_step_dialog") and self._step_dialog:
                self._step_dialog.dismiss()

        self._step_dialog = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogSupportingText(text=content_text[:2000]),  # cap for dialog display
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="OK"), style="text", on_release=_close),
            ),
        )
        self._step_dialog.open()
