"""
DiagnosticsPanel — hub_panel for diagnostics plugin.

Features:
  - Run Validation: checks mods, dependencies, file presence via deploy validator (if available)
  - Package Logs: collect ap_framework.log + UE4SS.log + sanitized config → ZIP
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.label import MDLabel

from ...gui.widgets.plugin_panel import PluginPanel

if TYPE_CHECKING:
    from ...core.config import GameProfile


_STATUS_COLOR = {
    "ok":    (0.3, 0.8, 0.4, 1),
    "warn":  (0.95, 0.75, 0.1, 1),
    "error": (0.9, 0.3, 0.3, 1),
}


class _ResultRow(MDBoxLayout):
    def __init__(self, label: str, detail: str, status: str, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(40),
            spacing=dp(8),
            padding=[dp(4), 0],
            **kwargs,
        )
        color = _STATUS_COLOR.get(status, (0.6, 0.6, 0.6, 1))
        icon_map = {"ok": "✓", "warn": "⚠", "error": "✗"}
        self.add_widget(MDLabel(
            text=icon_map.get(status, "?"),
            size_hint=(None, 1),
            width=dp(24),
            halign="center",
            theme_text_color="Custom",
            text_color=color,
        ))
        self.add_widget(MDLabel(
            text=f"[b]{label}[/b]  {detail}" if detail else f"[b]{label}[/b]",
            markup=True,
            size_hint=(1, 1),
            halign="left",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.9, 0.9, 0.9, 1),
        ))


class DiagnosticsPanel(PluginPanel):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)
        self._host = host
        self._profile: Optional["GameProfile"] = None
        self._detection = None
        self._build_ui()

    # -----------------------------------------------------------------------
    # PluginPanel lifecycle
    # -----------------------------------------------------------------------

    def on_activate(self, game_profile: "GameProfile") -> None:
        self._profile = game_profile
        self._detection = self._host.get_detection()
        self._clear_results()

    def on_deactivate(self) -> None:
        pass

    # -----------------------------------------------------------------------
    # UI
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.orientation = "vertical"

        toolbar = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56),
                              md_bg_color=(0.15, 0.2, 0.25, 1), padding=(dp(8), 0))
        toolbar.add_widget(MDLabel(text="Diagnostics", font_style="Title", role="large",
                                   size_hint_x=1, halign="left"))
        self._toolbar = toolbar
        self.add_widget(toolbar)

        # Action buttons
        btn_row = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(56),
            spacing=dp(12),
            padding=[dp(16), dp(8)],
        )
        btn_row.add_widget(MDButton(
            MDButtonText(text="Run Validation"),
            style="filled",
            on_release=lambda *_: self._on_validate(),
        ))
        btn_row.add_widget(MDButton(
            MDButtonText(text="Package Logs"),
            style="filled",
            on_release=lambda *_: threading.Thread(
                target=self._on_package_logs, daemon=True
            ).start(),
        ))
        self.add_widget(btn_row)

        # Results area
        self._scroll = ScrollView(size_hint=(1, 1))
        self._results_layout = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(2),
            padding=[dp(16), dp(8)],
        )
        self._scroll.add_widget(self._results_layout)
        self.add_widget(self._scroll)

    def _clear_results(self) -> None:
        self._results_layout.clear_widgets()
        self._results_layout.add_widget(MDLabel(
            text="Press 'Run Validation' to check your setup.",
            halign="center",
            size_hint=(1, None),
            height=dp(48),
        ))

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    def _on_validate(self) -> None:
        if not self._detection:
            self._show_error("No game context — cannot validate.")
            return

        self._results_layout.clear_widgets()

        # UE4SS presence
        self._add_result(
            "UE4SS detected",
            str(self._detection.ue4ss_dir or ""),
            "ok" if self._detection.valid else "error",
        )

        # Missing components
        for missing in (self._detection.missing or []):
            self._add_result(f"Missing: {missing}", "", "error")

        # Mod validation (via deploy service's mods_txt + validator)
        mods_svc = self._host.get_service("mods")
        deploy_svc = self._host.get_service("deploy")
        if mods_svc and deploy_svc and deploy_svc.mods_txt:
            from ...plugins.deploy.validator import Validator
            mods_txt = deploy_svc.mods_txt
            mods = mods_svc.scan()
            validator = Validator(self._detection, mods_txt, mods)
        elif mods_svc and self._detection.mods_txt:
            # Fallback: deploy plugin not loaded, create our own mods_txt reader
            from ...plugins.deploy.mods_txt import ModsTextManager
            from ...plugins.deploy.validator import Validator
            mods_txt = ModsTextManager(self._detection.mods_txt)
            mods_txt.load()
            mods = mods_svc.scan()
            validator = Validator(self._detection, mods_txt, mods)
        else:
            validator = None
            mods = []

        if validator:
            for mod in mods:
                results = validator.validate_mod(mod)
                for r in results:
                    if r.status != "ok":
                        self._add_result(
                            f"{mod.display_name}: {r.label}",
                            r.detail,
                            r.status,
                        )

            if not any(
                r.status != "ok"
                for mod in mods
                for r in validator.validate_mod(mod)
            ):
                self._add_result("All mod checks passed", "", "ok")
        else:
            self._add_result(
                "Mod validation skipped",
                "Mods service not available",
                "warn",
            )

        self._host.log("Validation complete.")

    def _add_result(self, label: str, detail: str, status: str) -> None:
        self._results_layout.add_widget(
            _ResultRow(label=label, detail=detail, status=status)
        )

    def _show_error(self, msg: str) -> None:
        self._results_layout.clear_widgets()
        self._results_layout.add_widget(MDLabel(
            text=msg,
            halign="center",
            size_hint=(1, None),
            height=dp(48),
        ))

    # -----------------------------------------------------------------------
    # Log packaging
    # -----------------------------------------------------------------------

    def _on_package_logs(self) -> None:
        if not self._profile or not self._detection:
            Clock.schedule_once(
                lambda dt: self._host.log("No game context — cannot package logs."), 0
            )
            return

        from .log_packager import LogPackager
        packager = LogPackager(self._profile, self._detection)
        filename = LogPackager.suggested_filename(self._profile.display_name)

        # Save to user's Desktop (or home if Desktop absent)
        desktop = Path.home() / "Desktop"
        if not desktop.is_dir():
            desktop = Path.home()
        out_path = desktop / filename

        included = packager.collect(out_path)
        msg = f"Log package saved: {out_path.name}\n  Included: {', '.join(included)}"
        Clock.schedule_once(lambda dt, m=msg: self._host.log(m), 0)
