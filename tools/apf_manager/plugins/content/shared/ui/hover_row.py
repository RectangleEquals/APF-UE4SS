"""HoverRow — animated hover-highlight MDBoxLayout."""

from kivy.animation import Animation
from kivymd.uix.behaviors import HoverBehavior
from kivymd.uix.boxlayout import MDBoxLayout

from .constants import HOVER_DURATION_IN, HOVER_DURATION_OUT, HOVER_TARGET_ALPHA


class HoverRow(HoverBehavior, MDBoxLayout):
    """MDBoxLayout with animated hover feedback — used for expandable rows."""

    _hovering = False

    def on_enter(self):
        if self._hovering:
            return
        self._hovering = True
        from kivy.core.window import Window
        Window.set_system_cursor("hand")
        current_alpha = (self.md_bg_color or [0, 0, 0, 0])[3]
        remaining = HOVER_TARGET_ALPHA - current_alpha
        if remaining <= 0:
            return
        duration = max(HOVER_DURATION_IN * (remaining / HOVER_TARGET_ALPHA), 0.01)
        Animation(md_bg_color=(1, 1, 1, HOVER_TARGET_ALPHA), duration=duration).start(self)

    def on_leave(self):
        if not self._hovering:
            return
        self._hovering = False
        from kivy.core.window import Window
        Window.set_system_cursor("arrow")
        current_alpha = (self.md_bg_color or [0, 0, 0, 0])[3]
        if current_alpha <= 0:
            return
        duration = max(HOVER_DURATION_OUT * (current_alpha / HOVER_TARGET_ALPHA), 0.01)
        Animation(md_bg_color=(0, 0, 0, 0), duration=duration).start(self)

    def on_parent(self, widget, parent):
        if parent is None:
            self._hovering = False
            from kivy.core.window import Window
            Window.set_system_cursor("arrow")
            Animation.cancel_all(self, "md_bg_color")
            self.md_bg_color = (0, 0, 0, 0)