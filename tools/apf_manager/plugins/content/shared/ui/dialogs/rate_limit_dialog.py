"""RateLimitDialog — GitHub API rate limit notification dialog."""
from __future__ import annotations

from typing import Optional, Callable

from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogButtonContainer,
)


class RateLimitDialog:
    """
    Informs the user that a GitHub API rate limit has been hit.

    Parameters
    ----------
    reset_str    : str — human-readable reset time (e.g. "2026-04-30 12:00 UTC")
    is_search    : bool — True for search rate limit, False for general API limit
    on_close     : Callable[[], None] | None
    """

    def __init__(
        self,
        reset_str: str = "",
        is_search: bool = False,
        on_close: Optional[Callable] = None,
    ):
        self._reset_str = reset_str
        self._is_search = is_search
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

        if self._is_search:
            headline = "GitHub Search Limit Reached"
            body = (
                "The GitHub search API allows 30 requests per minute. "
                "Registry search is temporarily unavailable."
            )
        else:
            headline = "GitHub Rate Limit Reached"
            body = (
                "Too many requests have been made to the GitHub API. "
                "Registry browsing is unavailable until the limit resets."
            )

        if self._reset_str:
            body += f"\n\nExpected to reset at: {self._reset_str}"

        return MDDialog(
            MDDialogHeadlineText(text=headline),
            MDDialogSupportingText(text=body),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text="OK"), style="text", on_release=_close),
            ),
        )
