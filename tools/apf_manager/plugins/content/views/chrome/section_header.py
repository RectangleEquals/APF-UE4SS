"""make_section_header — unified collapsible section header factory."""

from typing import Callable, Optional

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel

from .constants import BG_SECTION, COL_SECTION, COL_DIM


def make_section_header(
    title: str,
    icon: str,
    count: int = 0,
    accent_color: tuple = (0.5, 0.5, 0.7, 1),
    subtitle: str = "",
    collapsed: bool = False,
    on_toggle: Optional[Callable[[str], None]] = None,
) -> MDBoxLayout:
    """Left accent bar + icon + title/count label + chevron. Click calls on_toggle(title)."""
    outer = MDBoxLayout(
        orientation="horizontal", size_hint_y=None, height=dp(36),
        md_bg_color=BG_SECTION,
    )
    outer.add_widget(MDBoxLayout(
        size_hint=(None, 1), width=dp(3),
        md_bg_color=accent_color,
    ))
    inner = MDBoxLayout(
        orientation="horizontal", size_hint=(1, 1),
        padding=[dp(8), 0], spacing=dp(8),
    )
    inner.add_widget(MDIcon(
        icon=icon, size_hint=(None, 1), width=dp(22),
        theme_icon_color="Custom", icon_color=COL_SECTION,
    ))
    label = f"{title}  ({count})" if count else title
    if subtitle:
        label += f"  — {subtitle}"
    inner.add_widget(MDLabel(
        text=label, font_style="Title", role="small",
        size_hint_x=1, halign="left",
        theme_text_color="Custom", text_color=COL_SECTION,
    ))
    inner.add_widget(MDIcon(
        icon="chevron-right" if collapsed else "chevron-down",
        size_hint=(None, 1), width=dp(22),
        theme_icon_color="Custom", icon_color=COL_DIM,
    ))
    outer.add_widget(inner)

    if on_toggle:
        def _on_touch(widget, touch):
            if widget.collide_point(*touch.pos) and touch.button == "left":
                on_toggle(title)
                return True
        outer.bind(on_touch_down=_on_touch)

    return outer