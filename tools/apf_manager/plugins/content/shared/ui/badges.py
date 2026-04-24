"""Badge widget builders — icon badges, text badges, component status chips."""

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel

from .constants import COL_STATUS_OK, COL_STATUS_MISS


def badge_icon(icon: str, color, tooltip: str = "") -> MDBoxLayout:
    """20dp wide icon badge."""
    box = MDBoxLayout(size_hint=(None, 1), width=dp(20))
    box.add_widget(MDIcon(
        icon=icon, size_hint=(None, 1), width=dp(16),
        theme_icon_color="Custom", icon_color=color,
    ))
    return box


def badge_text(text: str, color) -> MDLabel:
    """Bracketed [text] label badge."""
    return MDLabel(
        text=f"[{text}]", font_style="Label", role="small",
        size_hint=(None, 1), width=dp(90),
        halign="left", valign="middle",
        theme_text_color="Custom", text_color=color,
    )


def component_status_chip(component: str, ok: bool) -> MDBoxLayout:
    """80dp Lua/C++/BP chip with check/close icon and status color."""
    _labels = {"lua": "Lua", "cpp": "C++", "blueprint": "BP"}
    color = COL_STATUS_OK if ok else COL_STATUS_MISS
    chip = MDBoxLayout(
        orientation="horizontal", size_hint=(None, 1),
        width=dp(80), spacing=dp(4),
    )
    chip.add_widget(MDIcon(
        icon="check-circle-outline" if ok else "close-circle-outline",
        size_hint=(None, 1), width=dp(16),
        theme_icon_color="Custom", icon_color=color,
    ))
    chip.add_widget(MDLabel(
        text=_labels.get(component, component),
        font_style="Label", role="small",
        size_hint=(1, 1), halign="left", valign="middle",
        theme_text_color="Custom", text_color=color,
    ))
    return chip