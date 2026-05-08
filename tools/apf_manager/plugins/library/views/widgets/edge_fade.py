from __future__ import annotations

from kivy.graphics import Color, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.uix.widget import Widget


class EdgeFadeWidget(Widget):
    """Draws left and right alpha-fade gradients; touch events pass through."""

    _FADE_W = dp(40)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._left_rect = None
        self._right_rect = None
        self._build_canvas()
        self.bind(pos=self._update_rects, size=self._update_rects)

    def _build_canvas(self) -> None:
        left_tex = Texture.create(size=(2, 1), colorfmt="rgba")
        left_tex.blit_buffer(bytes([0, 0, 0, 200, 0, 0, 0, 0]),
                              colorfmt="rgba", bufferfmt="ubyte")
        left_tex.mag_filter = "linear"

        right_tex = Texture.create(size=(2, 1), colorfmt="rgba")
        right_tex.blit_buffer(bytes([0, 0, 0, 0, 0, 0, 0, 200]),
                               colorfmt="rgba", bufferfmt="ubyte")
        right_tex.mag_filter = "linear"

        with self.canvas:
            Color(1, 1, 1, 1)
            self._left_rect = Rectangle(
                texture=left_tex, pos=self.pos, size=(self._FADE_W, self.height),
            )
            self._right_rect = Rectangle(
                texture=right_tex,
                pos=(self.right - self._FADE_W, self.y),
                size=(self._FADE_W, self.height),
            )

    def _update_rects(self, *_) -> None:
        if self._left_rect:
            self._left_rect.pos = self.pos
            self._left_rect.size = (self._FADE_W, self.height)
        if self._right_rect:
            self._right_rect.pos = (self.right - self._FADE_W, self.y)
            self._right_rect.size = (self._FADE_W, self.height)

    def on_touch_down(self, touch):  return False
    def on_touch_move(self, touch):  return False
    def on_touch_up(self, touch):    return False
