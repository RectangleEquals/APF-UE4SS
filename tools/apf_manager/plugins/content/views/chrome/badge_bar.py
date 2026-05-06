"""BadgeBar — horizontal badge container with fixed height and overflow protection."""

from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout


class BadgeBar(MDBoxLayout):
    """Horizontal badge row with fixed height dp(22). Prevents layout overflow."""

    def __init__(self, spacing=None, padding=None, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(22),
            spacing=dp(8) if spacing is None else spacing,
            padding=padding or [dp(36), 0, dp(8), 0],
            **kwargs,
        )
