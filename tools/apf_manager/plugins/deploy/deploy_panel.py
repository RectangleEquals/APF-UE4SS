"""
DeployPanel — hub_panel UI for the deploy plugin.

Layout:
    [Top toolbar: Mods label | All switch | Rescan | Deploy All | Validate]
    [Sticky header: Order | Status | Mod Name | (Steps) | Version | Enabled]
    [Mod list: scrollable rows]
        Row: ▲▼ | status icon | name | step buttons | version | enable toggle
    [LogPanel at bottom (shared via host)]

Mod row color coding:
    default  — normal AP mod
    amber    — warning (unmet prefers_after, warns)
    red      — error (missing dep, incompatible)
    grey     — disabled
    dim text — non-AP mod row (not managed by APF)

Show All (default off): when off, only AP mods are shown.
_SCAN_EXCLUDE: folder names always excluded from the list regardless of Show All.
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
from kivymd.uix.selectioncontrol import MDSwitch

from ...gui.widgets.plugin_panel import PluginPanel
from ...gui.widgets.tip_icon_button import TipIconButton

if TYPE_CHECKING:
    from ...core.config import GameProfile
    from ...core.ue4ss import UE4SSResult
    from ..mods.mod_service import ModInfo, ModService
    from .validator import ValidationResult


_ROW_BG_NORMAL   = (0.14, 0.14, 0.14, 1)
_ROW_BG_WARN     = (0.22, 0.18, 0.08, 1)
_ROW_BG_ERROR    = (0.22, 0.10, 0.10, 1)
_ROW_BG_DISABLED = (0.10, 0.10, 0.10, 1)
_ROW_BG_NONAP    = (0.11, 0.11, 0.11, 1)

# Folders excluded from the mod list regardless of Show All state
_SCAN_EXCLUDE = {"shared"}

# Fixed column widths
_COL_REORDER = dp(64)   # ▲▼ buttons (or spacer)
_COL_STATUS  = dp(28)   # status MDIcon
_COL_STEPS   = dp(80)   # manual-step buttons container (or spacer)
_COL_VERSION = dp(72)   # version string (right-aligned)
_COL_TOGGLE  = dp(52)   # MDSwitch (or spacer)


# ---------------------------------------------------------------------------
# ModRow widget
# ---------------------------------------------------------------------------

class ModRow(MDBoxLayout):
    def __init__(
        self,
        mod: "ModInfo",
        status: str,
        enabled: bool,
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
        self._enabled = enabled
        self._build(on_toggle, on_move_up, on_move_down, on_manual_step)
        self._apply_row_color(status, mod)

    def _apply_row_color(self, status: str, mod: "ModInfo") -> None:
        if not mod.is_ap_mod:
            self.md_bg_color = _ROW_BG_NONAP
        elif not self._enabled:
            self.md_bg_color = _ROW_BG_DISABLED
        elif status == "error":
            self.md_bg_color = _ROW_BG_ERROR
        elif status == "warn":
            self.md_bg_color = _ROW_BG_WARN
        else:
            self.md_bg_color = _ROW_BG_NORMAL

    def _build(self, on_toggle, on_move_up, on_move_down, on_manual_step) -> None:
        mod = self._mod

        # Column 1: Reorder buttons (AP mods) or spacer
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
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=_COL_REORDER))

        # Column 2: Status badge
        from kivymd.uix.label import MDIcon
        from ...gui.theme import STATUS_ICONS
        icon_name, icon_color = STATUS_ICONS.get(self._status, STATUS_ICONS["unknown"])
        badge = MDIcon(
            icon=icon_name,
            theme_icon_color="Custom",
            icon_color=icon_color,
            size_hint=(None, 1),
            width=_COL_STATUS,
            halign="center",
            valign="middle",
        )
        self.add_widget(badge)

        # Column 3: Mod name (flexible)
        name_lbl = MDLabel(
            text=mod.display_name,
            font_style="Body",
            size_hint=(1, 1),
            halign="left",
            valign="middle",
            theme_text_color="Custom" if not mod.is_ap_mod else "Primary",
            text_color=(0.5, 0.5, 0.5, 1) if not mod.is_ap_mod else (1, 1, 1, 0.87),
        )
        self.add_widget(name_lbl)

        # Column 4: Manual step buttons (or spacer) — fixed width for column alignment
        button_steps = [s for s in mod.manual_steps if s.when == "button" and s.caption]
        if button_steps:
            steps_box = MDBoxLayout(
                orientation="horizontal",
                size_hint=(None, 1),
                width=_COL_STEPS,
                spacing=dp(2),
            )
            for step in button_steps:
                btn = MDButton(
                    MDButtonText(text=step.caption),
                    style="text",
                    size_hint=(1, 1),
                    on_release=lambda *_, s=step: on_manual_step(mod, s),
                )
                steps_box.add_widget(btn)
            self.add_widget(steps_box)
        else:
            self.add_widget(Widget(size_hint=(None, 1), width=_COL_STEPS))

        # Column 5: Version (fixed width, right-aligned, small right padding)
        version_lbl = MDLabel(
            text=f"v{mod.version}" if mod.version else "",
            font_style="Label",
            role="small",
            size_hint=(None, 1),
            width=_COL_VERSION,
            halign="right",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
            padding=[0, 0, dp(4), 0],
        )
        self.add_widget(version_lbl)

        # Column 6: Enable/disable toggle (AP mods only)
        if mod.is_ap_mod:
            cb = MDSwitch(size_hint=(None, None), pos_hint={"center_y": 0.5})
            cb.active = self._enabled
            cb.bind(active=lambda inst, val, m=mod: on_toggle(m, val))
            self._checkbox = cb
            self.add_widget(cb)
        else:
            self.add_widget(MDBoxLayout(size_hint=(None, 1), width=_COL_TOGGLE))


# ---------------------------------------------------------------------------
# Header row (sticky, above ScrollView)
# ---------------------------------------------------------------------------

class _HeaderRow(MDBoxLayout):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(28),
            padding=[dp(4), 0],
            spacing=dp(4),
            md_bg_color=(0.12, 0.12, 0.12, 1),
            **kwargs,
        )

        def _col(text: str, width=None, halign: str = "left"):
            kw = dict(
                text=text,
                font_style="Label",
                role="small",
                valign="middle",
                halign=halign,
                theme_text_color="Custom",
                text_color=(0.55, 0.55, 0.55, 1),
            )
            if width is not None:
                kw["size_hint"] = (None, 1)
                kw["width"] = width
            else:
                kw["size_hint"] = (1, 1)
            return MDLabel(**kw)

        self.add_widget(_col("Order", width=_COL_REORDER, halign="center"))
        self.add_widget(_col("Status", width=_COL_STATUS, halign="center"))
        self.add_widget(_col("Mod Name"))
        self.add_widget(_col("", width=_COL_STEPS))
        self.add_widget(_col("Version", width=_COL_VERSION, halign="right"))
        self.add_widget(_col("Enabled", width=_COL_TOGGLE, halign="center"))


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
        self._show_all: bool = False
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
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            md_bg_color=(0.15, 0.2, 0.25, 1),
            padding=(dp(8), 0),
            spacing=dp(4),
        )
        toolbar.add_widget(MDLabel(
            text="Mods",
            font_style="Title",
            role="large",
            size_hint_x=1,
            halign="left",
        ))

        # "Show All" toggle
        toolbar.add_widget(MDLabel(
            text="All",
            size_hint=(None, 1),
            width=dp(24),
            halign="center",
            theme_text_color="Custom",
            text_color=(0.7, 0.7, 0.7, 1),
        ))
        self._show_all_switch = MDSwitch(size_hint=(None, None), pos_hint={"center_y": 0.5})
        self._show_all_switch.active = False
        self._show_all_switch.bind(active=lambda inst, val: self._on_show_all_toggle(val))
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
        toolbar.add_widget(TipIconButton(
            icon="check-circle",
            tooltip_text="Validate load order",
            on_release=lambda *_: self._on_validate(),
        ))
        self._toolbar = toolbar
        self.add_widget(toolbar)

        # Sticky header (hidden until mods are present)
        self._header_row = _HeaderRow()
        self._header_row.opacity = 0
        self.add_widget(self._header_row)

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
    # Data loading
    # -----------------------------------------------------------------------

    def _get_mods(self) -> list["ModInfo"]:
        svc = self._host.get_service("mods")
        return svc.scan() if svc else []

    def _refresh(self) -> None:
        self._list_layout.clear_widgets()
        self._rows = []

        mods = self._get_mods()

        # Always exclude non-mod folders
        mods = [m for m in mods if m.folder_name not in _SCAN_EXCLUDE]

        # Filter to AP mods only unless Show All is on
        if not self._show_all:
            mods = [m for m in mods if m.is_ap_mod]

        if not mods:
            self._header_row.opacity = 0
            self._list_layout.add_widget(MDLabel(
                text="No mods found in this game's Mods directory.",
                halign="center",
                size_hint=(1, None),
                height=dp(60),
            ))
            return

        self._header_row.opacity = 1

        # Sort mods by mods.txt order (mods not yet in mods.txt go at end)
        if self._mods_txt:
            order = self._mods_txt.get_order()
            order_idx = {name: i for i, name in enumerate(order)}
            mods.sort(key=lambda m: order_idx.get(m.folder_name, len(order)))

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
                if self._mods_txt.contains(mod.folder_name):
                    enabled = self._mods_txt.is_enabled(mod.folder_name)
                else:
                    enabled = True
            else:
                enabled = True

            row = ModRow(
                mod=mod,
                status=status,
                enabled=enabled,
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

    def _on_show_all_toggle(self, val: bool) -> None:
        self._show_all = val
        self._refresh()

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
        mods = [m for m in mods if m.folder_name not in _SCAN_EXCLUDE]
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
        idx = next(
            (i for i, r in enumerate(self._rows) if r._mod.folder_name == mod.folder_name),
            None,
        )
        if idx is None or idx == 0:
            return
        self._swap_displayed(idx, idx - 1)

    def _on_move_down(self, mod: "ModInfo") -> None:
        idx = next(
            (i for i, r in enumerate(self._rows) if r._mod.folder_name == mod.folder_name),
            None,
        )
        if idx is None or idx >= len(self._rows) - 1:
            return
        self._swap_displayed(idx, idx + 1)

    def _swap_displayed(self, i: int, j: int) -> None:
        """Swap rows[i] and rows[j] in the display order, then rebuild and save mods.txt order."""
        svc = self._deploy_svc
        if not svc:
            return

        # New display order after swap
        rows = self._rows[:]
        rows[i], rows[j] = rows[j], rows[i]
        displayed_names_new = [r._mod.folder_name for r in rows]
        displayed_names_set = {r._mod.folder_name for r in self._rows}

        # Rebuild full mods.txt order: keep hidden mods in their original positions,
        # replace displayed mods with the new display order.
        full_order = svc.get_load_order()
        new_full: list[str] = []
        di = 0
        for name in full_order:
            if name in displayed_names_set:
                new_full.append(displayed_names_new[di])
                di += 1
            else:
                new_full.append(name)

        # Append any displayed mods not yet in mods.txt (new/undeployed)
        while di < len(displayed_names_new):
            new_full.append(displayed_names_new[di])
            di += 1

        svc.reorder(new_full)
        self._refresh()

    def _on_manual_step(self, mod: "ModInfo", step) -> None:
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

            if not self._host.has_service("docs_viewer"):
                self._show_enable_docs_notice()
                return

            # docs_viewer present but file not resolved — fall through to text
            content_text = step.content or f"Follow the instructions for: {step.caption}"
        else:
            content_text = step.content or f"Follow the instructions for: {step.caption}"

        def _close(*_):
            if hasattr(self, "_step_dialog") and self._step_dialog:
                self._step_dialog.dismiss()

        self._step_dialog = MDDialog(
            MDDialogHeadlineText(text=title),
            MDDialogSupportingText(text=content_text[:2000]),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="OK"), style="text", on_release=_close),
            ),
        )
        self._step_dialog.open()

    def _show_enable_docs_notice(self) -> None:
        from kivymd.app import MDApp

        def _go_settings(*_):
            if dlg[0]:
                dlg[0].dismiss()
            app = MDApp.get_running_app()
            if app:
                app.root.current = "settings"

        def _dismiss(*_):
            if dlg[0]:
                dlg[0].dismiss()

        dlg = [None]
        dlg[0] = MDDialog(
            MDDialogHeadlineText(text="Feature Not Enabled"),
            MDDialogSupportingText(
                text="This feature isn't currently enabled.\nEnable the Docs Viewer plugin in Settings to enable."
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="OK"), style="text", on_release=_dismiss),
                MDButton(MDButtonText(text="Go to Settings"), style="filled",
                         on_release=_go_settings),
            ),
        )
        dlg[0].open()
