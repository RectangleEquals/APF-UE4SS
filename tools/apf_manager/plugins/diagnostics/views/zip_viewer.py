"""
ZipViewer — widget that renders the contents of a diagnostics ZIP file.

Shows a scrollable list of entries (filename + size).
Clicking an entry opens a sub-dialog with the file's text content.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)
from kivymd.uix.label import MDLabel


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 ** 2:.1f} MB"


class _EntryRow(MDBoxLayout):
    def __init__(self, name: str, size: int, on_open, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(44),
            spacing=dp(8),
            padding=[dp(4), 0],
            **kwargs,
        )
        self.add_widget(MDLabel(
            text=name,
            size_hint=(1, 1),
            halign="left",
            valign="middle",
        ))
        self.add_widget(MDLabel(
            text=_fmt_size(size),
            size_hint=(None, 1),
            width=dp(72),
            halign="right",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
        ))
        self.add_widget(MDButton(
            MDButtonText(text="View"),
            style="text",
            size_hint=(None, 1),
            width=dp(56),
            on_release=lambda *_: on_open(name),
        ))


class ZipViewer(MDBoxLayout):
    def __init__(self, zip_path: str, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._zip_path = zip_path
        self._content_dialog: MDDialog | None = None
        self._build(zip_path)

    def _build(self, zip_path: str) -> None:
        header = MDLabel(
            text=Path(zip_path).name,
            font_style="Title",
            role="small",
            size_hint=(1, None),
            height=dp(32),
            halign="left",
            padding=[dp(8), 0],
            theme_text_color="Custom",
            text_color=(0.7, 0.8, 1.0, 1),
        )
        self.add_widget(header)

        scroll = ScrollView(size_hint=(1, 1))
        layout = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(2),
            padding=[dp(8), dp(4)],
        )

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                entries = sorted(zf.infolist(), key=lambda e: e.filename)
                if not entries:
                    layout.add_widget(MDLabel(
                        text="(empty archive)",
                        halign="center",
                        size_hint=(1, None),
                        height=dp(40),
                    ))
                for entry in entries:
                    layout.add_widget(_EntryRow(
                        name=entry.filename,
                        size=entry.file_size,
                        on_open=self._open_entry,
                    ))
        except Exception as exc:
            layout.add_widget(MDLabel(
                text=f"Could not open ZIP: {exc}",
                halign="center",
                size_hint=(1, None),
                height=dp(40),
                theme_text_color="Custom",
                text_color=(0.9, 0.3, 0.3, 1),
            ))

        scroll.add_widget(layout)
        self.add_widget(scroll)

    def _open_entry(self, name: str) -> None:
        try:
            with zipfile.ZipFile(self._zip_path, "r") as zf:
                raw = zf.read(name)
                try:
                    text = raw.decode("utf-8", errors="replace")
                except Exception:
                    text = repr(raw[:512])
        except Exception as exc:
            text = f"Could not read entry: {exc}"

        display = text[:4000]
        if len(text) > 4000:
            display += f"\n\n… ({len(text) - 4000} more chars truncated)"

        def _close(*_):
            if self._content_dialog:
                self._content_dialog.dismiss()
                self._content_dialog = None

        self._content_dialog = MDDialog(
            MDDialogHeadlineText(text=name),
            MDDialogSupportingText(text=display),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Close"), style="text", on_release=_close),
            ),
        )
        self._content_dialog.open()
