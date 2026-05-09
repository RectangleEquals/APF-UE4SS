"""BranchRow + BranchHeaderRow for the DevTools Source Control tab."""
from __future__ import annotations

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.button import MDButton, MDButtonIcon, MDButtonText, MDIconButton
from kivymd.uix.label import MDLabel

from .data_row import DevDataRow, DevHeaderRow

_COLS = [("Name", 0.65), ("Status", 0.25), ("", None)]


def make_branch_header() -> DevHeaderRow:
    return DevHeaderRow.from_columns(_COLS)


class BranchRow(DevDataRow):
    """
    One row in the Branches list: name / status-or-action / delete button.

    Protected branches show a status label instead of a delete button.
    """

    def __init__(
        self,
        branch: dict,
        on_delete: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(hover=True, **kwargs)
        bname     = branch.get("name", "?")
        protected = branch.get("protected", False) or bname in ("master", "main")

        self._name_lbl = MDLabel(text=bname, adaptive_height=True, size_hint_x=0.65)

        if protected:
            self._action_widget: MDLabel | MDButton = MDLabel(
                text="protected" if branch.get("protected", False) else "default",
                adaptive_height=True,
                size_hint_x=0.25,
                theme_text_color="Secondary",
            )
        else:
            self._action_widget = MDButton(
                MDButtonIcon(icon="delete-outline"),
                MDButtonText(text="Delete"),
                style="text",
                size_hint_x=0.25,
            )
            if on_delete:
                self._action_widget.bind(
                    on_release=lambda *_, n=bname: on_delete(n))

        self._del_btn = MDIconButton(icon="delete", size_hint_x=None, width=dp(36))
        self._del_btn.disabled = True
        self._del_btn.opacity = 0

        for w in (self._name_lbl, self._action_widget, self._del_btn):
            self.add_widget(w)
