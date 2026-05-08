"""
DocsPanel — service interface for the docs viewer.

Registered as both the "docs_viewer" service and dialog contribution.
Delegates all operations to DocsController.
"""

from __future__ import annotations

from ..controllers.controller import DocsController


class DocsPanel:
    """
    Thin proxy registered as the "docs_viewer" service.
    All logic lives in DocsController.
    """

    def __init__(self, host) -> None:
        self._ctrl = DocsController(host)

    def open(self, path=None, initial_path=None, force_dev_docs=False,
             sidebar_mode="default", show_mode_toggle=True) -> None:
        self._ctrl.open(
            path=path,
            initial_path=initial_path,
            force_dev_docs=force_dev_docs,
            sidebar_mode=sidebar_mode,
            show_mode_toggle=show_mode_toggle,
        )

    def open_local_spa(self, path, title="", sidebar_mode="default",
                       show_mode_toggle=True, show_sidebar=True) -> None:
        self._ctrl.open_local_spa(
            path=path, title=title, sidebar_mode=sidebar_mode,
            show_mode_toggle=show_mode_toggle, show_sidebar=show_sidebar,
        )

    def open_url(self, url, title="", show_sidebar=False,
                 show_mode_toggle=False, sidebar_mode="verbose") -> None:
        self._ctrl.open_url(
            url=url, title=title, show_sidebar=show_sidebar,
            show_mode_toggle=show_mode_toggle, sidebar_mode=sidebar_mode,
        )

    def show_inline(self, content, title="Release Notes",
                    sidebar_mode="verbose", allow_mode_toggle=False) -> None:
        self._ctrl.show_inline(
            content=content, title=title,
            sidebar_mode=sidebar_mode, allow_mode_toggle=allow_mode_toggle,
        )
