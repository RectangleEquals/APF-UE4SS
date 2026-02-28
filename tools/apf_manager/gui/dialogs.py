"""
APF Manager — dialog helpers for manual_steps popups and file viewer.
"""

from __future__ import annotations

from pathlib import Path

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton
from kivymd.uix.label import MDLabel


def show_step_dialog(step: dict, source_project: str = "") -> None:
    """Display a manual_steps entry in a dialog window."""
    title = step.get("title", "Information")
    step_type = step.get("type", "text")
    content_val = step.get("content", "")

    if step_type == "file":
        text = _load_file(content_val, source_project)
    else:
        text = content_val

    # MDDialog(type="custom") places content_cls inside its own ScrollView,
    # so content_cls should be an MDBoxLayout with computable height.
    content = MDBoxLayout(orientation="vertical", size_hint_y=None, padding="4dp")
    label = MDLabel(
        text=text,
        size_hint_y=None,
        markup=False,
        text_size=(dp(400), None),
    )
    label.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
    content.add_widget(label)
    content.bind(minimum_height=content.setter("height"))

    dialog = MDDialog(
        title=title,
        type="custom",
        content_cls=content,
        size_hint=(0.85, 0.75),
        buttons=[
            MDFlatButton(text="Close", on_release=lambda x: dialog.dismiss()),
        ],
    )
    dialog.open()


def _load_file(rel_path: str, source_project: str) -> str:
    """Load a file relative to source_project. Returns its text content."""
    if not rel_path:
        return "(No content specified)"
    try:
        base = Path(source_project) if source_project else Path.cwd()
        path = base / rel_path
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        return f"(File not found: {path})"
    except Exception as exc:
        return f"(Error reading file: {exc})"
