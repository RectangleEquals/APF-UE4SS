"""ReleaseRow + ReleaseHeaderRow for the DevTools CI tab."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel

from .data_row import DevDataRow, DevHeaderRow

_COLS = [("Tag", 0.25), ("Name", 0.55), ("View", None)]


def make_release_header() -> DevHeaderRow:
    return DevHeaderRow.from_columns(_COLS)


class ReleaseRow(DevDataRow):
    """One row in the Releases list: tag / name / View button."""

    def __init__(
        self,
        release: dict,
        on_view: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(hover=True, **kwargs)
        tag  = release.get("tag_name", "?")
        name = release.get("name", "")
        url  = release.get("html_url", "")

        self._tag_lbl = MDLabel(text=tag, adaptive_height=True, size_hint_x=0.25)
        self._name_lbl = MDLabel(
            text=name, adaptive_height=True, size_hint_x=0.55,
            theme_text_color="Secondary")
        self._view_btn = MDIconButton(icon="open-in-new", size_hint_x=None, width=dp(36))
        if url and on_view:
            self._view_btn.bind(on_release=lambda *_, u=url: on_view(u))
        else:
            self._view_btn.disabled = True

        for w in (self._tag_lbl, self._name_lbl, self._view_btn):
            self.add_widget(w)
