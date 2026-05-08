from __future__ import annotations

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel

from .edge_fade import EdgeFadeWidget
from .game_tile import TILE_W, TILE_H


CAROUSEL_H = dp(175)


class _PlaceholderTile(MDCard):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(TILE_W, TILE_H),
            md_bg_color=(0.18, 0.18, 0.18, 1),
            **kwargs,
        )
        with self.canvas.before:
            Color(0.18, 0.18, 0.18, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd, size=self._upd)
        self.add_widget(MDLabel(
            text="?",
            font_style="Display",
            role="small",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.38, 0.38, 0.38, 1),
        ))

    def _upd(self, *_) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size


class AddGameTile(MDCard):
    """Always-first tile in the Custom Games section."""

    def __init__(self, on_add, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(TILE_W, TILE_H),
            md_bg_color=(0.2, 0.2, 0.2, 1),
            **kwargs,
        )
        self._on_add = on_add
        self._build()

    def _build(self) -> None:
        with self.canvas.before:
            Color(0.2, 0.2, 0.2, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        plus_area = MDBoxLayout(size_hint=(1, 1), orientation="vertical")
        plus_area.add_widget(MDLabel(
            text="+",
            font_style="Display",
            role="large",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.6, 1),
        ))
        self.add_widget(plus_area)

        name_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(28),
            padding=[dp(6), dp(2)],
            md_bg_color=(0, 0, 0, 0.5),
        )
        name_bar.add_widget(MDLabel(
            text="Add Custom Game",
            font_style="Label",
            role="small",
            halign="left",
            valign="middle",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(1, 1, 1, 0.9),
        ))
        self.add_widget(name_bar)
        self.bind(on_release=lambda *_: self._on_add())

    def _update_bg(self, *_) -> None:
        self._bg.pos = self.pos
        self._bg.size = self.size


class CarouselSection(MDBoxLayout):
    """Section header + horizontally-scrolling tile carousel with edge fades."""

    def __init__(self, title: str, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(1, None),
            adaptive_height=True,
            spacing=dp(4),
            padding=[dp(16), dp(8), dp(16), dp(4)],
            **kwargs,
        )
        self.bind(minimum_height=self.setter("height"))

        header = MDBoxLayout(size_hint=(1, None), height=dp(32))
        header.add_widget(MDLabel(
            text=title,
            font_style="Title",
            role="large",
            size_hint_x=1,
            halign="left",
            valign="middle",
        ))
        self.add_widget(header)

        row = FloatLayout(size_hint=(1, None), height=CAROUSEL_H)

        self._scroll = ScrollView(
            do_scroll_x=True,
            do_scroll_y=False,
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
            bar_width=0,
        )
        self._tiles_box = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=1,
            size_hint_x=None,
            spacing=dp(12),
            padding=[dp(40), dp(12), dp(40), dp(12)],
        )
        self._tiles_box.bind(minimum_width=self._tiles_box.setter("width"))
        self._scroll.add_widget(self._tiles_box)

        row.add_widget(self._scroll)
        row.add_widget(EdgeFadeWidget(size_hint=(1, 1), pos_hint={"x": 0, "y": 0}))
        self.add_widget(row)

        self._scroll.bind(width=lambda *_: Clock.schedule_once(
            lambda dt: self._reflow_placeholders(), 0))

    def clear_tiles(self) -> None:
        self._tiles_box.clear_widgets()

    def add_tile(self, tile: Widget) -> None:
        self._tiles_box.add_widget(tile)

    @property
    def tile_count(self) -> int:
        return len(self._tiles_box.children)

    def adjust_placeholders(self, n_real: int) -> None:
        slot_w = TILE_W + dp(12)
        usable_w = max(self._scroll.width - dp(80), 0)
        visible_slots = max(int(usable_w / slot_w) + 1, 0)
        n_needed = max(0, visible_slots - n_real)

        placeholders = [c for c in reversed(self._tiles_box.children)
                        if isinstance(c, _PlaceholderTile)]
        while len(placeholders) > n_needed:
            tile = placeholders.pop()
            self._tiles_box.remove_widget(tile)
        while len(placeholders) < n_needed:
            tile = _PlaceholderTile()
            self._tiles_box.add_widget(tile)
            placeholders.append(tile)

    def _reflow_placeholders(self) -> None:
        n_real = sum(1 for c in self._tiles_box.children
                     if not isinstance(c, _PlaceholderTile))
        self.adjust_placeholders(n_real)
