"""StatusRowWidget — icon + label + optional detail line. Used in install_tab and registries_tab."""

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel


class StatusRowWidget(MDBoxLayout):
    """Single-row display: icon + primary label + optional dimmed detail text."""

    def __init__(
        self,
        icon: str,
        icon_color,
        label: str,
        detail: str = "",
        row_height: float = None,
        **kwargs,
    ):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(row_height) if row_height is not None else dp(28),
            spacing=dp(8),
            **kwargs,
        )
        self.add_widget(MDIcon(
            icon=icon,
            size_hint=(None, 1),
            width=dp(20),
            theme_icon_color="Custom",
            icon_color=icon_color,
        ))
        self.add_widget(MDLabel(
            text=label,
            font_style="Label",
            role="small",
            size_hint=(1, 1),
            halign="left",
            valign="middle",
        ))
        if detail:
            self.add_widget(MDLabel(
                text=detail,
                font_style="Label",
                role="small",
                size_hint=(None, 1),
                width=dp(160),
                halign="right",
                valign="middle",
                theme_text_color="Custom",
                text_color=(0.5, 0.5, 0.5, 1),
            ))
