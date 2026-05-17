"""ReleaseRow + make_release_header for the DevTools CI tab."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel

from .data_row import DevDataRow, DevHeaderRow

# Fixed column widths (dp) — shared by header and data rows so they always align
# regardless of ScrollView scrollbar width.
_W_TAG  = 100
_W_NAME = 250
_W_VIEW = 36

_COLS = [("Tag", None), ("Name", None), ("View", None)]
_FIXED_WIDTHS = {0: dp(_W_TAG), 1: dp(_W_NAME), 2: dp(_W_VIEW)}


def make_release_header() -> DevHeaderRow:
    return DevHeaderRow.from_columns(_COLS, fixed_widths=_FIXED_WIDTHS)


class ReleaseRow(DevDataRow):
    """One row in the Releases list: tag / name / View button."""

    def __init__(
        self,
        release: dict,
        on_view: Optional[Callable[[str], None]] = None,
        row_index: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(hover=True, row_index=row_index, **kwargs)
        tag  = release.get("tag_name", "?")
        name = release.get("name", "")
        url  = release.get("html_url", "")

        self._tag_lbl = MDLabel(
            text=tag,
            adaptive_height=True,
            size_hint_x=None,
            width=dp(_W_TAG),
        )
        self._name_lbl = MDLabel(
            text=name,
            adaptive_height=True,
            size_hint_x=None,
            width=dp(_W_NAME),
            theme_text_color="Secondary",
        )
        self._view_btn = MDIconButton(
            icon="open-in-new",
            size_hint_x=None,
            width=dp(_W_VIEW),
        )
        if url and on_view:
            self._view_btn.bind(on_release=lambda *_, u=url: on_view(u))
        else:
            self._view_btn.disabled = True

        for w in (self._tag_lbl, self._name_lbl, self._view_btn):
            self.add_widget(w)
