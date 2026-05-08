from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, PushMatrix, PopMatrix, Rectangle, Scale, Translate
from kivy.metrics import dp
from kivy.properties import NumericProperty
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDIcon, MDLabel
from kivy.uix.widget import Widget

from .....core.views.theme import STATUS_ICONS as _BADGE_STATUS

if TYPE_CHECKING:
    from .....core.models.config import GameProfile


TILE_W = dp(200)
TILE_H = dp(150)

_TILE_COLORS = [
    (0.18, 0.28, 0.42, 1),
    (0.22, 0.35, 0.28, 1),
    (0.38, 0.22, 0.22, 1),
    (0.32, 0.28, 0.18, 1),
    (0.28, 0.22, 0.38, 1),
    (0.18, 0.35, 0.38, 1),
    (0.38, 0.28, 0.18, 1),
    (0.22, 0.22, 0.38, 1),
]


def tile_color(name: str) -> tuple:
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(_TILE_COLORS)
    return _TILE_COLORS[idx]


class GameTile(MDCard):
    """Single game tile in a library carousel. Animates via canvas scale on hover."""

    _scale_factor = NumericProperty(1.0)

    def __init__(self, profile: "GameProfile", on_select, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(TILE_W, TILE_H),
            md_bg_color=(0.12, 0.12, 0.12, 1),
            **kwargs,
        )
        self._profile = profile
        self._on_select = on_select
        self._bg_rect: Optional[Rectangle] = None
        self._translate_to: Optional[Translate] = None
        self._translate_back: Optional[Translate] = None
        self._scale_instr: Optional[Scale] = None
        self._badge_icon: Optional[MDIcon] = None
        self._badge_lbl: Optional[MDLabel] = None
        self._hovered = False
        self._hover_anim: Optional[Animation] = None
        self._img_area: Optional[MDBoxLayout] = None
        self._build()

    def _build(self) -> None:
        color = tile_color(self._profile.display_name)

        with self.canvas.before:
            PushMatrix()
            self._translate_to = Translate(0, 0)
            self._scale_instr = Scale(1, 1, 1)
            self._translate_back = Translate(0, 0)
            Color(*color)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        with self.canvas.after:
            PopMatrix()

        self.bind(pos=self._sync_canvas, size=self._sync_canvas,
                  _scale_factor=self._sync_scale)

        self._img_area = MDBoxLayout(size_hint=(1, 1), orientation="vertical")
        thumb = self._profile.custom_thumbnail
        if thumb and Path(thumb).is_file():
            self._set_thumbnail(Path(thumb))
        else:
            self._img_area.add_widget(MDLabel(
                text="?",
                font_style="Display",
                role="small",
                halign="center",
                valign="middle",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.18),
            ))
        self.add_widget(self._img_area)

        name_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(28),
            padding=[dp(6), dp(2)],
            md_bg_color=(0, 0, 0, 0.62),
        )
        name_bar.add_widget(MDLabel(
            text=self._profile.display_name,
            font_style="Label",
            role="small",
            halign="left",
            valign="middle",
            shorten=True,
            shorten_from="right",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(1, 1, 1, 0.9),
        ))
        self.add_widget(name_bar)

        badge_row = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(24),
            padding=[0, 0, dp(4), 0],
            spacing=dp(2),
        )
        badge_row.add_widget(Widget(size_hint_x=1))

        self._badge_icon = MDIcon(
            icon="help-circle",
            theme_icon_color="Custom",
            icon_color=(0.5, 0.5, 0.5, 1),
            font_size="16sp",
            size_hint=(None, None),
            size=(dp(20), dp(20)),
            halign="center",
            valign="middle",
        )
        self._badge_lbl = MDLabel(
            text="UE4SS",
            font_style="Label",
            role="small",
            halign="left",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.5, 0.5, 0.5, 1),
            size_hint=(None, 1),
            width=dp(48),
        )
        badge_row.add_widget(self._badge_icon)
        badge_row.add_widget(self._badge_lbl)
        self.add_widget(badge_row)

        self.bind(on_release=lambda *_: self._on_select(self._profile))

    def _sync_canvas(self, *_) -> None:
        if self._bg_rect:
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size
        self._sync_scale()

    def _sync_scale(self, *_) -> None:
        if self._translate_to is None:
            return
        cx, cy = self.center
        self._translate_to.x = cx
        self._translate_to.y = cy
        self._scale_instr.x = self._scale_factor
        self._scale_instr.y = self._scale_factor
        self._translate_back.x = -cx
        self._translate_back.y = -cy

    def on_parent(self, instance, parent) -> None:
        if parent is not None:
            Window.bind(mouse_pos=self._on_mouse_pos)
        else:
            Window.unbind(mouse_pos=self._on_mouse_pos)

    def _on_mouse_pos(self, window, pos) -> None:
        wx, wy = self.to_window(self.x, self.y)
        wr, wt = self.to_window(self.right, self.top)
        inside = wx <= pos[0] <= wr and wy <= pos[1] <= wt

        if inside and not self._hovered:
            self._hovered = True
            if self._hover_anim:
                self._hover_anim.cancel(self)
            self._hover_anim = Animation(_scale_factor=1.06, d=0.12, t="out_quad")
            self._hover_anim.start(self)
        elif not inside and self._hovered:
            self._hovered = False
            if self._hover_anim:
                self._hover_anim.cancel(self)
            self._hover_anim = Animation(_scale_factor=1.0, d=0.12, t="out_quad")
            self._hover_anim.start(self)

    def set_thumbnail(self, path: Path) -> None:
        Clock.schedule_once(lambda dt: self._set_thumbnail(path), 0)

    def _set_thumbnail(self, path: Path) -> None:
        from kivy.uix.image import Image
        self._img_area.clear_widgets()
        self._img_area.add_widget(Image(source=str(path), fit_mode="fill"))

    def set_ue4ss_badge(self, status: str) -> None:
        icon_name, color = _BADGE_STATUS.get(status, _BADGE_STATUS["unknown"])
        if self._badge_icon:
            self._badge_icon.icon = icon_name
            self._badge_icon.icon_color = color
        if self._badge_lbl:
            self._badge_lbl.text_color = color
