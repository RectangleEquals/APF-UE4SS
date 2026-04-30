"""ChangelogDialog — read-only release notes / changelog viewer."""
from __future__ import annotations

from typing import Optional, Callable

from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)

_MAX_CHANGELOG_CHARS = 500


class ChangelogDialog:
    """
    Read-only dialog showing release notes or a changelog excerpt.

    Parameters
    ----------
    title     : str — dialog headline (e.g. "Release Notes")
    changelog : str — changelog text (truncated to 500 chars)
    on_close  : Callable[[], None] | None
    """

    def __init__(
        self,
        title: str = "Release Notes",
        changelog: str = "",
        on_close: Optional[Callable] = None,
    ):
        self._title = title
        self._changelog = changelog[:_MAX_CHANGELOG_CHARS]
        self._on_close = on_close
        self._dialog: Optional[MDDialog] = None

    def open(self) -> None:
        if self._dialog:
            return
        self._dialog = self._build()
        self._dialog.open()

    def _build(self) -> MDDialog:
        def _close(*_):
            if self._dialog:
                self._dialog.dismiss()
            self._dialog = None
            if self._on_close:
                self._on_close()

        return MDDialog(
            MDDialogHeadlineText(text=self._title),
            MDDialogSupportingText(text=self._changelog or "(no release notes available)"),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="Close"), style="text", on_release=_close),
            ),
        )
