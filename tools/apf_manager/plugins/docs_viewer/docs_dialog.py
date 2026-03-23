"""
DocsDialog — full-screen dialog for browsing and rendering Markdown docs.

Can be opened:
  - Via the hub_action toolbar button (opens to docs/public/dev/ file browser)
  - Via host.show_dialog("docs_viewer", path="docs/public/dev/mods.md")
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogContentContainer, MDDialogButtonContainer,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.list import MDList, MDListItem, MDListItemHeadlineText

def _docs_root() -> Path:
    """Resolve the docs/public/dev/ directory relative to the project root."""
    if getattr(sys, "frozen", False):
        # In a frozen build, docs are bundled next to the executable
        return Path(sys.executable).parent / "docs" / "public" / "dev"
    # Development: go up from tools/apf_manager/plugins/docs_viewer/ to project root
    return Path(__file__).parents[4] / "docs" / "public" / "dev"


class DocsDialog:
    """
    Manager for the docs viewer dialog.
    Call .open(path=None) to show.
    """

    def __init__(self) -> None:
        self._dialog: Optional[MDDialog] = None

    def open(self, path: Optional[str] = None) -> None:
        content = _DocsContent(initial_path=path)

        def _close(*_):
            if self._dialog:
                self._dialog.dismiss()

        self._dialog = MDDialog(
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Close"), style="text", on_release=_close),
            ),
        )
        self._dialog.open()


class _DocsContent(MDBoxLayout):
    """Dialog body: file tree on the left, rendered doc on the right."""

    def __init__(self, initial_path: Optional[str] = None, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint=(1, 1),
            **kwargs,
        )
        self._docs_root = _docs_root()
        self._build()

        if initial_path:
            target = Path(initial_path)
            if not target.is_absolute():
                # Relative: resolve from project root
                target = Path(__file__).parents[4] / initial_path
            self._load_file(target)
        else:
            self._load_index()

    def _build(self) -> None:
        # Left: file tree
        tree_panel = MDBoxLayout(
            orientation="vertical",
            size_hint=(0.3, 1),
        )
        tree_panel.add_widget(MDLabel(
            text="Documents",
            font_style="Title",
            size_hint=(1, None),
            height=dp(36),
            halign="center",
        ))
        tree_scroll = ScrollView()
        self._tree_list = MDList()
        tree_scroll.add_widget(self._tree_list)
        tree_panel.add_widget(tree_scroll)
        self.add_widget(tree_panel)

        self._populate_tree()

        # Right: doc content
        content_panel = MDBoxLayout(orientation="vertical", size_hint=(0.7, 1))
        self._content_scroll = ScrollView()
        self._content_area = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            padding=[dp(12), dp(8)],
        )
        self._content_scroll.add_widget(self._content_area)
        content_panel.add_widget(self._content_scroll)
        self.add_widget(content_panel)

    def _populate_tree(self) -> None:
        self._tree_list.clear_widgets()
        if not self._docs_root.is_dir():
            self._tree_list.add_widget(MDListItem(MDListItemHeadlineText(text="(docs not found)")))
            return
        for f in sorted(self._docs_root.rglob("*.md")):
            rel = f.relative_to(self._docs_root)
            item = MDListItem(
                MDListItemHeadlineText(text=str(rel)),
                on_release=lambda _, p=f: self._load_file(p),
            )
            self._tree_list.add_widget(item)

    def _load_index(self) -> None:
        index = self._docs_root / "README.md"
        if index.exists():
            self._load_file(index)
        else:
            self._show_placeholder("Select a document from the list.")

    def _load_file(self, path: Path) -> None:
        self._content_area.clear_widgets()
        if not path.exists():
            self._show_placeholder(f"File not found:\n{path}")
            return
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            self._show_placeholder(f"Could not read file:\n{exc}")
            return

        from .markdown_renderer import render_markdown
        rendered = render_markdown(text)
        self._content_area.add_widget(rendered)
        # Reset scroll
        self._content_scroll.scroll_y = 1

    def _show_placeholder(self, msg: str) -> None:
        self._content_area.clear_widgets()
        self._content_area.add_widget(MDLabel(
            text=msg,
            halign="center",
            size_hint=(1, None),
            height=dp(80),
        ))
