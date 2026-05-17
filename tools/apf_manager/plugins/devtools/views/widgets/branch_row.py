"""BranchRow + make_branch_header for the DevTools Source Control tab."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.button import MDIconButton
from kivymd.uix.label import MDLabel

from .data_row import DevDataRow, DevHeaderRow

# Fixed-width columns (dp).  Name is flexible (size_hint_x=1).
_W_STATUS = 100
_W_DELETE = 72   # wide enough for the "Delete" header label; icon button centered within

_COLS = [("Name", 1), ("Status", None), ("Delete", None)]
_FIXED_WIDTHS = {1: dp(_W_STATUS), 2: dp(_W_DELETE)}


def make_branch_header() -> DevHeaderRow:
    return DevHeaderRow.from_columns(_COLS, fixed_widths=_FIXED_WIDTHS)


class BranchRow(DevDataRow):
    """
    One row in the Branches list: Name | Status | Delete.

    Protected / default branches show a status label and a disabled Delete button.
    Unprotected branches show an empty status and an active Delete button.
    """

    def __init__(
        self,
        branch: dict,
        on_delete: Optional[Callable[[str], None]] = None,
        row_index: int = 0,
        **kwargs,
    ) -> None:
        super().__init__(hover=True, row_index=row_index, **kwargs)
        bname     = branch.get("name", "?")
        protected = branch.get("protected", False) or bname in ("master", "main")

        status_text = ("protected" if branch.get("protected", False) else "default") if protected else ""

        self._name_lbl = MDLabel(
            text=bname,
            size_hint_x=1,
            size_hint_y=1,
            valign="middle",
            halign="left",
        )
        self._status_lbl = MDLabel(
            text=status_text,
            size_hint_x=None,
            width=dp(_W_STATUS),
            size_hint_y=1,
            valign="middle",
            halign="left",
            theme_text_color="Secondary",
        )
        self._del_btn = MDIconButton(
            icon="delete-outline",
            size_hint=(None, None),
            width=dp(_W_DELETE),
            height=dp(36),
            pos_hint={"center_y": 0.5},
            disabled=protected,
        )
        if not protected and on_delete:
            self._del_btn.bind(on_release=lambda *_, n=bname: on_delete(n))

        for w in (self._name_lbl, self._status_lbl, self._del_btn):
            self.add_widget(w)
