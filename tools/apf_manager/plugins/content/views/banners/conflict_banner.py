"""ConflictBanner — framework mod conflict warning banner."""

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDIcon, MDLabel


class ConflictBanner(MDBoxLayout):
    """
    Red banner shown when multiple framework mod installations are detected.

    Parameters
    ----------
    conflict_paths : list — Path objects or strings identifying conflicting installs
    """

    def __init__(self, conflict_paths: list, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            md_bg_color=(0.22, 0.06, 0.06, 1),
            padding=[dp(12), 0],
            spacing=dp(8),
            **kwargs,
        )
        names = ", ".join(
            p.name if hasattr(p, "name") else str(p) for p in conflict_paths
        )
        self.add_widget(MDIcon(
            icon="alert-octagon",
            size_hint=(None, 1), width=dp(24),
            theme_icon_color="Custom", icon_color=(1.0, 0.3, 0.3, 1),
        ))
        self.add_widget(MDLabel(
            text=(
                "Multiple framework mods detected — resolve conflict before managing mods.\n"
                f"Conflicting: {names}"
            ),
            theme_text_color="Custom", text_color=(1.0, 0.5, 0.5, 1),
            font_style="Body", role="small",
        ))
