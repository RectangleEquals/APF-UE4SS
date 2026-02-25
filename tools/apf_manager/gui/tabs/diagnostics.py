"""
APF Manager — Diagnostics tab.

Runs validation checks and provides log packaging for dev support.
"""

from __future__ import annotations

from kivy.uix.scrollview import ScrollView
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDFlatButton, MDRaisedButton
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.tab import MDTabsBase

# Status colors
_STATUS_COLOR = {
    "OK": (0.1, 0.6, 0.1, 1),
    "WARN": (0.8, 0.6, 0.0, 1),
    "ERROR": (0.8, 0.1, 0.1, 1),
}


class DiagnosticsTab(MDFloatLayout, MDTabsBase):
    title = "Diagnostics"

    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self._build()

    def _build(self):
        layout = MDBoxLayout(
            orientation="vertical",
            padding="16dp",
            spacing="8dp",
        )

        btn_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height="48dp",
            spacing="8dp",
        )
        validate_btn = MDRaisedButton(
            text="Validate Installation",
            size_hint=(None, None),
            size=("200dp", "40dp"),
        )
        validate_btn.bind(on_release=self._on_validate)
        pkg_logs_btn = MDFlatButton(
            text="Package Logs for Dev",
            size_hint=(None, None),
            size=("180dp", "40dp"),
        )
        pkg_logs_btn.bind(on_release=self._on_package_logs)
        btn_row.add_widget(validate_btn)
        btn_row.add_widget(pkg_logs_btn)
        layout.add_widget(btn_row)

        self._status_label = MDLabel(
            text="Click 'Validate Installation' to run checks.",
            size_hint_y=None,
            height="32dp",
            theme_text_color="Secondary",
        )
        layout.add_widget(self._status_label)

        scroll = ScrollView(size_hint=(1, 1))
        self._results_box = MDBoxLayout(
            orientation="vertical",
            spacing="4dp",
            size_hint_y=None,
        )
        self._results_box.bind(minimum_height=self._results_box.setter("height"))
        scroll.add_widget(self._results_box)
        layout.add_widget(scroll)

        self.add_widget(layout)

    def on_tab_activated(self):
        pass  # Don't auto-run; let user click the button

    def _on_validate(self, *_):
        from ...validator import Validator
        detection = self.app.refresh_detection()
        if not detection.valid:
            self._status_label.text = f"UE4SS not detected: {'; '.join(detection.missing)}"
            return

        v = Validator(
            self.app.config_data,
            self.app.discovery,
            self.app.state,
            detection,
        )
        results = v.validate_all()
        self._display_results(results)

    def _display_results(self, results: list[tuple[str, str, str]]):
        self._results_box.clear_widgets()
        ok = sum(1 for s, _, _ in results if s == "OK")
        warn = sum(1 for s, _, _ in results if s == "WARN")
        err = sum(1 for s, _, _ in results if s == "ERROR")
        self._status_label.text = (
            f"Results: {ok} OK  |  {warn} warnings  |  {err} errors"
        )
        for status, label, detail in results:
            row = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height="32dp",
                spacing="8dp",
            )
            status_lbl = MDLabel(
                text=f"[{status}]",
                size_hint_x=None,
                width="60dp",
                theme_text_color="Custom",
                text_color=_STATUS_COLOR.get(status, (0.5, 0.5, 0.5, 1)),
                font_style="Caption",
            )
            content_lbl = MDLabel(
                text=f"{label}: {detail}",
                font_style="Caption",
                theme_text_color="Primary",
            )
            row.add_widget(status_lbl)
            row.add_widget(content_lbl)
            self._results_box.add_widget(row)

    def _on_package_logs(self, *_):
        from ...packager import LogPackager
        from pathlib import Path
        detection = self.app.refresh_detection()
        if not detection.valid:
            self._status_label.text = "UE4SS not detected."
            return
        try:
            out_dir = Path(self.app.config_data.source_project) / "tools" / "dist"
            packager = LogPackager(detection)
            out = packager.build(out_dir)
            self._status_label.text = f"Logs packaged: {out}"
        except Exception as exc:
            self._status_label.text = f"Error: {exc}"
