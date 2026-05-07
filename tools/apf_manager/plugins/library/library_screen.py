"""
LibraryScreen — game library home screen.

Sections (horizontal carousels):
  - Steam Games  (hidden when no steam games detected)
  - Custom Games (always shown; "Add Custom Game" tile always first)

Features:
  - Add Custom Game: folder picker → UE root resolution → post-add details dialog
  - Card hover: canvas scale animation (no layout reflow)
  - Edge fade: gradient overlays on each carousel
  - UE4SS badge: MDIconButton icon + text label (replaces unicode)
  - Placeholder tiles (TEMP — remove after visual testing)
"""

from __future__ import annotations

import hashlib
import threading
import webbrowser
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, PushMatrix, PopMatrix, Rectangle, Scale, Translate
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogContentContainer, MDDialogButtonContainer,
)
from kivymd.uix.label import MDIcon, MDLabel
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivymd.uix.textfield import MDTextField


class _DotBadgeButton(MDBoxLayout):
    """MDIconButton wrapped in a layout that supports a red dot overlay badge."""

    has_badge = BooleanProperty(False)

    def __init__(self, icon: str, on_release=None, **kwargs):
        super().__init__(
            size_hint=(None, None), size=(dp(48), dp(48)), **kwargs
        )
        self._btn = MDIconButton(
            icon=icon, size_hint=(1, 1),
        )
        if on_release:
            self._btn.bind(on_release=on_release)
        self.add_widget(self._btn)
        self.bind(has_badge=self._redraw, pos=self._redraw, size=self._redraw)

    def _redraw(self, *_) -> None:
        self.canvas.after.clear()
        if not self.has_badge:
            return
        dot_r = dp(5)
        bx = self.right - dp(10)
        by = self.top - dp(10)
        with self.canvas.after:
            Color(1.0, 0.25, 0.25, 1)
            Ellipse(pos=(bx - dot_r, by - dot_r), size=(dot_r * 2, dot_r * 2))

    def set_badge(self, visible: bool) -> None:
        self.has_badge = visible

if TYPE_CHECKING:
    from ...core.controllers.plugin_host import PluginHost
    from ...core.models.config import APFConfig, GameProfile


# ---------------------------------------------------------------------------
# Tile colour palette (deterministic from game display_name hash)
# ---------------------------------------------------------------------------

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


def _tile_color(name: str) -> tuple:
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(_TILE_COLORS)
    return _TILE_COLORS[idx]


# UE4SS badge: uses shared STATUS_ICONS from theme
from ...core.views.theme import STATUS_ICONS as _BADGE_STATUS
from ...core.views.widgets.tip_icon_button import ImageIconButton

_TILE_W = dp(200)
_TILE_H = dp(150)

_DISCORD_ICON = Path(__file__).parent.parent.parent / "data" / "Discord_Symbol_White.png"
# Path(__file__).parent = plugins/library/ → .parent.parent = plugins/ → .parent.parent.parent = apf_manager/
# Works for plugins (always real disk files, not in library.zip)


# ---------------------------------------------------------------------------
# UE root detection helpers
# ---------------------------------------------------------------------------

def _has_content_paks(path: Path) -> bool:
    """True if path/Content/Paks exists."""
    try:
        return (path / "Content" / "Paks").is_dir()
    except (PermissionError, OSError):
        return False


def _dirs_at_depth(path: Path, depth: int) -> list[Path]:
    """All directories exactly `depth` levels below `path`."""
    if depth == 0:
        return [path]
    result: list[Path] = []
    try:
        for child in path.iterdir():
            if child.is_dir():
                result.extend(_dirs_at_depth(child, depth - 1))
    except (PermissionError, OSError):
        pass
    return result


def _find_ue_root(selected: Path) -> Optional[Path]:
    """
    Given any path the user selected, resolve to the UE game_root
    (parent of the <short_name> directory that contains Content/Paks).

    UE game structure: <game_root>/<short_name>/Content/Paks
    The user may select game_root, short_name, or any deeper path.
    """
    # Step 1: drill down from selected (up to 3 levels).
    # If `candidate` IS the <short_name> (has Content/Paks), return its parent.
    for depth in range(4):
        for candidate in _dirs_at_depth(selected, depth):
            if _has_content_paks(candidate):
                return candidate.parent

    # Step 2: walk up — try each ancestor as game_root.
    # A valid game_root has at least one child whose Content/Paks exists.
    for root_candidate in [selected, *selected.parents]:
        try:
            for child in root_candidate.iterdir():
                if child.is_dir() and _has_content_paks(child):
                    return root_candidate
        except (PermissionError, OSError):
            continue
    return None


def _detect_game_name(game_root: Path) -> str:
    """Auto-detect a display name from the game root folder name."""
    return game_root.name.replace("_", " ").replace("-", " ").title()


# ---------------------------------------------------------------------------
# EdgeFadeWidget — transparent overlay with left/right gradient fades
# ---------------------------------------------------------------------------

class EdgeFadeWidget(Widget):
    """Draws left and right alpha-fade gradients; touch events pass through."""

    _FADE_W = dp(40)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._left_rect: Optional[Rectangle] = None
        self._right_rect: Optional[Rectangle] = None
        self._build_canvas()
        self.bind(pos=self._update_rects, size=self._update_rects)

    def _build_canvas(self) -> None:
        # Left: opaque → transparent (left to right)
        left_tex = Texture.create(size=(2, 1), colorfmt="rgba")
        left_tex.blit_buffer(bytes([0, 0, 0, 200, 0, 0, 0, 0]),
                              colorfmt="rgba", bufferfmt="ubyte")
        left_tex.mag_filter = "linear"

        # Right: transparent → opaque (left to right)
        right_tex = Texture.create(size=(2, 1), colorfmt="rgba")
        right_tex.blit_buffer(bytes([0, 0, 0, 0, 0, 0, 0, 200]),
                               colorfmt="rgba", bufferfmt="ubyte")
        right_tex.mag_filter = "linear"

        with self.canvas:
            Color(1, 1, 1, 1)
            self._left_rect = Rectangle(
                texture=left_tex, pos=self.pos,
                size=(self._FADE_W, self.height),
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


# ---------------------------------------------------------------------------
# GameTile
# ---------------------------------------------------------------------------

class GameTile(MDCard):
    """Single game tile in a library carousel. Animates via canvas scale on hover."""

    _scale_factor = NumericProperty(1.0)

    def __init__(self, profile: "GameProfile", on_select, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(_TILE_W, _TILE_H),
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
        color = _tile_color(self._profile.display_name)

        # Canvas: push matrix → translate to centre → scale → translate back
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

        # Image area (flexible)
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

        # Name bar (fixed 28dp)
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

        # UE4SS badge row (fixed 24dp): spacer | icon | "UE4SS" label
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

    # --- Canvas sync ---

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

    # --- Hover ---

    def on_parent(self, instance, parent) -> None:
        if parent is not None:
            Window.bind(mouse_pos=self._on_mouse_pos)
        else:
            Window.unbind(mouse_pos=self._on_mouse_pos)

    def _on_mouse_pos(self, window, pos) -> None:
        # Convert window pos to window-space tile bounds
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

    # --- Thumbnail ---

    def set_thumbnail(self, path: Path) -> None:
        Clock.schedule_once(lambda dt: self._set_thumbnail(path), 0)

    def _set_thumbnail(self, path: Path) -> None:
        from kivy.uix.image import Image
        self._img_area.clear_widgets()
        self._img_area.add_widget(Image(
            source=str(path),
            fit_mode="fill",
        ))

    # --- Badge ---

    def set_ue4ss_badge(self, status: str) -> None:
        icon_name, color = _BADGE_STATUS.get(status, _BADGE_STATUS["unknown"])
        if self._badge_icon:
            self._badge_icon.icon = icon_name
            self._badge_icon.icon_color = color
        if self._badge_lbl:
            self._badge_lbl.text_color = color


# ---------------------------------------------------------------------------
# _AddGameTile — always first in the Custom section
# ---------------------------------------------------------------------------

class _AddGameTile(MDCard):
    def __init__(self, on_add, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(_TILE_W, _TILE_H),
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


# ---------------------------------------------------------------------------
# _PlaceholderTile — TEMP: visual testing of carousel/fade/hover
# TODO: remove placeholder tiles after visual testing is complete
# ---------------------------------------------------------------------------

class _PlaceholderTile(MDCard):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(_TILE_W, _TILE_H),
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


# ---------------------------------------------------------------------------
# _CarouselSection — labeled section with horizontal carousel + edge fades
# ---------------------------------------------------------------------------

_CAROUSEL_H = dp(175)   # height of carousel row (150dp tiles + 12dp top/bottom padding)


class _CarouselSection(MDBoxLayout):
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

        # Section header
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

        # FloatLayout: ScrollView + EdgeFadeWidget overlay at same position
        row = FloatLayout(size_hint=(1, None), height=_CAROUSEL_H)

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
            padding=[dp(40), dp(12), dp(40), dp(12)],  # Fix 32-D: padding = fade width
        )
        self._tiles_box.bind(minimum_width=self._tiles_box.setter("width"))
        self._scroll.add_widget(self._tiles_box)

        row.add_widget(self._scroll)
        row.add_widget(EdgeFadeWidget(size_hint=(1, 1), pos_hint={"x": 0, "y": 0}))
        self.add_widget(row)

        # Fix 32-F: reflow placeholders when carousel width changes
        self._scroll.bind(width=lambda *_: Clock.schedule_once(
            lambda dt: self._reflow_placeholders(), 0))

    def clear_tiles(self) -> None:
        self._tiles_box.clear_widgets()

    def add_tile(self, tile: Widget) -> None:
        self._tiles_box.add_widget(tile)

    @property
    def tile_count(self) -> int:
        return len(self._tiles_box.children)

    def _adjust_placeholders(self, n_real: int) -> None:
        """Fill visible area with placeholder tiles without overflowing. Fix 32-F."""
        slot_w = _TILE_W + dp(12)
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
        self._adjust_placeholders(n_real)


# ---------------------------------------------------------------------------
# LibraryScreen
# ---------------------------------------------------------------------------

class LibraryScreen(MDBoxLayout):
    """
    Home screen — two labeled carousels: Steam and Custom Games.
    Folder-picker based Add Custom Game flow with UE root auto-detection.
    """

    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._config = config
        self._search_visible: bool = False
        self._search_text: str = ""
        self._steam_games: list = []
        self._thumbnail_cache = None
        self._tile_map: dict[str, "GameTile"] = {}
        self._steam_section: Optional[_CarouselSection] = None
        self._custom_section: Optional[_CarouselSection] = None
        self._settings_badge_btn: Optional["_DotBadgeButton"] = None
        self._build()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            md_bg_color=(0.15, 0.2, 0.25, 1),
            padding=(dp(8), 0),
            spacing=dp(4),
        )
        toolbar.add_widget(MDLabel(
            text="Game Library", font_style="Title", role="large",
            size_hint_x=1, halign="left",
        ))
        toolbar.add_widget(MDIconButton(
            icon="magnify", on_release=lambda *_: self._toggle_search()))
        toolbar.add_widget(MDIconButton(
            icon="refresh", on_release=lambda *_: threading.Thread(
                target=self._refresh_steam, daemon=True).start()))
        toolbar.add_widget(MDIconButton(
            icon="book-open-variant", on_release=lambda *_: self._open_docs()))
        if _DISCORD_ICON.exists():
            discord_btn = ImageIconButton(source=str(_DISCORD_ICON), tooltip_text="Join our Discord")
            discord_btn.bind(on_release=lambda *_: webbrowser.open("https://discord.gg/xhcVRhnjK"))
            toolbar.add_widget(discord_btn)
        self._settings_badge_btn = _DotBadgeButton(
            icon="cog", on_release=lambda *_: self._go_settings()
        )
        toolbar.add_widget(self._settings_badge_btn)
        self.add_widget(toolbar)

        # Collapsible search bar
        self._search_field = MDTextField(
            hint_text="Search games…",
            mode="outlined",
            size_hint=(1, None),
            height=0,
            opacity=0,
        )
        self._search_field.bind(text=self._on_search)
        self.add_widget(self._search_field)

        # Outer vertical scroll for all sections
        outer_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._sections_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
        )
        self._sections_box.bind(minimum_height=self._sections_box.setter("height"))

        self._steam_section = _CarouselSection("Steam")
        self._custom_section = _CarouselSection("Custom Games")
        self._sections_box.add_widget(self._steam_section)
        self._sections_box.add_widget(self._custom_section)

        outer_scroll.add_widget(self._sections_box)
        self.add_widget(outer_scroll)

        Clock.schedule_once(lambda dt: self._initial_load(), 0)

    # -----------------------------------------------------------------------
    # Load
    # -----------------------------------------------------------------------

    def _initial_load(self) -> None:
        self.refresh()
        threading.Thread(target=self._refresh_steam, daemon=True).start()
        # Wire update dot — check now (service's TTL handles re-check deduplication)
        if self._host.has_service("updates"):
            self._host.get_service("updates").check_all(
                on_done=self._apply_update_dot
            )

    def _apply_update_dot(self) -> None:
        """Show/hide the red dot on the settings gear based on update availability."""
        if self._settings_badge_btn is None:
            return
        updates_svc = (self._host.get_service("updates")
                       if self._host.has_service("updates") else None)
        if not updates_svc:
            return
        mgr = updates_svc.get_update_info("manager")
        apw = updates_svc.get_update_info("apworld")
        has_update = (
            (mgr and mgr.is_update_available)
            or (apw and apw.is_update_available)
        )
        self._settings_badge_btn.set_badge(bool(has_update))

    # -----------------------------------------------------------------------
    # Public
    # -----------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild both carousels."""
        self._steam_section.clear_tiles()
        self._custom_section.clear_tiles()
        self._tile_map.clear()

        steam_games, custom_games = self._partition_games()

        # --- Steam section ---
        for entry in steam_games:
            self._steam_section.add_tile(self._make_game_tile(entry))

        self._steam_section.opacity = 1

        # --- Custom section ---
        self._custom_section.add_tile(_AddGameTile(on_add=self._open_add_folder_picker))
        for entry in custom_games:
            self._custom_section.add_tile(self._make_game_tile(entry))

        # Fix 32-F: dynamic placeholder count (no placeholders during search)
        if not self._search_text:
            self._steam_section._adjust_placeholders(len(steam_games))
            self._custom_section._adjust_placeholders(1 + len(custom_games))

    def _make_game_tile(self, profile: "GameProfile") -> GameTile:
        tile = GameTile(profile=profile, on_select=self._on_tile_selected)
        self._tile_map[profile.game_id] = tile
        if profile.steam_app_id and self._get_thumbnail_cache():
            self._fetch_thumbnail(profile)
        threading.Thread(
            target=self._check_ue4ss_badge, args=(profile, tile), daemon=True,
        ).start()
        return tile

    def _partition_games(self) -> tuple[list, list]:
        """Split all games into (steam_games, custom_games), applying search filter."""
        from ...core.models.config import GameProfile

        config_games = list(self._config.games.values())
        config_app_ids = {p.steam_app_id for p in config_games if p.steam_app_id}

        # Config games with a steam_app_id → steam; without → custom
        config_steam = [g for g in config_games if g.steam_app_id]
        config_custom = [g for g in config_games if not g.steam_app_id]

        # Steam-scanned games not already in config → steam
        discovered_steam: list[GameProfile] = []
        for sg in self._steam_games:
            if sg.app_id not in config_app_ids:
                discovered_steam.append(GameProfile.new(
                    display_name=sg.name,
                    game_root=str(sg.install_dir),
                    steam_app_id=sg.app_id,
                ))

        steam = config_steam + discovered_steam
        custom = config_custom

        if self._search_text:
            q = self._search_text.lower()
            steam = [g for g in steam if q in g.display_name.lower()]
            custom = [g for g in custom if q in g.display_name.lower()]

        return steam, custom

    # -----------------------------------------------------------------------
    # Steam scan
    # -----------------------------------------------------------------------

    def _refresh_steam(self) -> None:
        try:
            from .steam_library import SteamLibrary
            override = self._config.steam_library_override
            lib = SteamLibrary(override_vdf_path=override)
            all_games = lib.scan()
            self._steam_games = [g for g in all_games if g.is_ue]
        except Exception:
            self._steam_games = []
        Clock.schedule_once(lambda dt: self.refresh(), 0)

    # -----------------------------------------------------------------------
    # Thumbnails
    # -----------------------------------------------------------------------

    def _get_thumbnail_cache(self):
        if self._thumbnail_cache is None:
            try:
                from .thumbnail_cache import ThumbnailCache
                self._thumbnail_cache = ThumbnailCache()
            except Exception:
                pass
        return self._thumbnail_cache

    def _fetch_thumbnail(self, profile: "GameProfile") -> None:
        cache = self._get_thumbnail_cache()
        if not cache or not profile.steam_app_id:
            return
        cached = cache.path(profile.steam_app_id)
        if cached:
            tile = self._tile_map.get(profile.game_id)
            if tile:
                tile._set_thumbnail(cached)
            return

        def _on_loaded(path):
            tile = self._tile_map.get(profile.game_id)
            if tile and path:
                Clock.schedule_once(lambda dt, p=path: tile._set_thumbnail(p), 0)

        cache.get(profile.steam_app_id, on_loaded=_on_loaded)

    # -----------------------------------------------------------------------
    # UE4SS badge
    # -----------------------------------------------------------------------

    def _check_ue4ss_badge(self, profile: "GameProfile", tile: GameTile) -> None:
        from ...core.controllers.detection import UE4SSDetector
        if not profile.game_root:
            status = "unknown"
        elif not Path(profile.game_root).is_dir():
            status = "error"
        else:
            detection = UE4SSDetector.detect(profile.game_root)
            if detection.valid:
                status = "ok"
            elif detection.content_paks_dir:
                status = "warn"   # UE game but UE4SS not installed
            else:
                status = "error"  # not a UE game root
        Clock.schedule_once(lambda dt, s=status: tile.set_ue4ss_badge(s), 0)

    # -----------------------------------------------------------------------
    # Tile click
    # -----------------------------------------------------------------------

    def _on_tile_selected(self, profile: "GameProfile") -> None:
        from ...core.controllers.detection import UE4SSDetector
        detection = UE4SSDetector.detect(profile.game_root)
        if detection.valid or detection.content_paks_dir:
            # Navigate even when UE4SS is absent — Tab 1 of Mods panel handles setup.
            if profile.game_id not in self._config.games:
                self._config.add_game(profile)
            self._host.navigate_to_game(profile)
        else:
            # Not a recognised UE game root at all.
            MDSnackbar(MDSnackbarText(
                text="Not a UE game folder — check the game root path."
            )).open()

    def _confirm_remove_game(self, profile: "GameProfile") -> None:
        dialog: list = []

        def _do_remove(*_):
            self._config.remove_game(profile.game_id)
            dialog[0].dismiss()
            self.refresh()

        def _cancel(*_):
            dialog[0].dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Remove from Library"),
            MDDialogSupportingText(
                text=(f"Remove \"{profile.display_name}\" from APF Manager?\n\n"
                      "This only removes the tile from the library — it does not "
                      "affect your game installation.")
            ),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text="Remove"), style="filled",
                         md_bg_color=(0.7, 0.1, 0.1, 1), on_release=_do_remove),
            ),
        )
        dialog.append(dlg)
        dlg.open()

    # -----------------------------------------------------------------------
    # Add Custom Game — folder picker flow
    # -----------------------------------------------------------------------

    def _open_add_folder_picker(self) -> None:
        # Tier 1 — native dialog via tkinter (most reliable)
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askdirectory(title="Select Game Folder")
            root.destroy()
            if path:
                Clock.schedule_once(lambda dt: self._on_dir_chosen([path]), 0)
            return
        except Exception as exc:
            self._host.log(f"[library] tkinter folder picker failed: {type(exc).__name__}: {exc}")

        # Tier 2 — plyer native abstraction
        try:
            from plyer import filechooser
            filechooser.choose_dir(
                title="Select Game Folder",
                on_selection=self._on_dir_chosen,
            )
            return
        except Exception as exc:
            self._host.log(f"[library] plyer folder picker failed: {type(exc).__name__}: {exc}")

        # Tier 3 — embedded Kivy FileChooser (last resort)
        self._host.log("[library] Falling back to Kivy folder picker.")
        self._open_kivy_folder_picker()

    def _open_kivy_folder_picker(self) -> None:
        from kivy.metrics import dp
        from kivy.uix.filechooser import FileChooserIconView

        picker = FileChooserIconView(
            path=str(Path.home()),
            dirselect=True,
            size_hint=(1, None),
            height=dp(400),
        )
        dialog: list = []

        def _select(*_):
            selection = picker.selection or [picker.path]
            dialog[0].dismiss()
            Clock.schedule_once(lambda dt: self._on_dir_chosen(selection), 0)

        def _cancel(*_):
            dialog[0].dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Select Game Folder"),
            MDDialogContentContainer(picker),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text="Select"), style="filled", on_release=_select),
            ),
        )
        dialog.append(dlg)
        dlg.open()

    def _on_dir_chosen(self, selection: list) -> None:
        if not selection:
            return
        selected = Path(selection[0])
        game_root = _find_ue_root(selected)
        if game_root is None:
            self._show_snackbar("Not a recognized Unreal Engine game folder.")
            return

        # Duplicate check
        existing_roots = {
            str(Path(p.game_root).resolve())
            for p in self._config.games.values()
            if p.game_root
        }
        if str(game_root.resolve()) in existing_roots:
            self._show_snackbar("This game is already in your library.")
            return

        self._open_add_details_dialog(game_root, _detect_game_name(game_root))

    def _open_add_details_dialog(self, game_root: Path, auto_name: str) -> None:
        chosen_image: list[Optional[str]] = [None]
        dialog: list = []

        image_status_lbl = MDLabel(
            text="No image selected",
            font_style="Label",
            role="small",
            halign="left",
            size_hint_x=1,
        )

        content = MDBoxLayout(
            orientation="vertical",
            spacing=dp(8),
            padding=[dp(4), dp(8)],
            size_hint_y=None,
            height=dp(156),
        )
        name_field = MDTextField(
            text=auto_name,
            hint_text="Game name",
            mode="outlined",
        )
        warning_lbl = MDLabel(
            text="Note: changing the name after deployment may cause issues.",
            font_style="Label",
            role="small",
            theme_text_color="Custom",
            text_color=(0.9, 0.7, 0.2, 1),
            size_hint_y=None,
            height=dp(36),
        )
        image_row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(40),
            spacing=dp(8),
        )
        image_btn = MDButton(
            MDButtonText(text="Pick Image…"),
            style="text",
            size_hint_x=None,
            width=dp(120),
            on_release=lambda *_: self._open_image_picker(chosen_image, image_status_lbl),
        )
        image_row.add_widget(image_status_lbl)
        image_row.add_widget(image_btn)

        content.add_widget(name_field)
        content.add_widget(warning_lbl)
        content.add_widget(image_row)

        def _confirm(*_):
            from ...core.models.config import GameProfile
            name = name_field.text.strip() or auto_name
            self._config.add_game(GameProfile.new(
                display_name=name,
                game_root=str(game_root),
                custom_thumbnail=chosen_image[0],
            ))
            self.refresh()
            dialog[0].dismiss()

        def _cancel(*_):
            dialog[0].dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Add Custom Game"),
            MDDialogSupportingText(text=str(game_root)),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text="Add"), style="filled", on_release=_confirm),
            ),
        )
        dialog.append(dlg)
        dlg.open()

    # -----------------------------------------------------------------------
    # Image picker
    # -----------------------------------------------------------------------

    def _open_image_picker(self, chosen_image: list, status_lbl: MDLabel) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="Select Thumbnail Image",
                filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
            )
            root.destroy()
            if path:
                Clock.schedule_once(
                    lambda dt: self._on_image_chosen([path], chosen_image, status_lbl), 0)
            return
        except Exception:
            pass
        try:
            from plyer import filechooser
            filechooser.open_file(
                title="Select Thumbnail Image",
                filters=[("Image files", "*.png", "*.jpg", "*.jpeg")],
                on_selection=lambda sel: self._on_image_chosen(sel, chosen_image, status_lbl),
            )
        except Exception:
            self._open_kivy_image_picker(chosen_image, status_lbl)

    def _open_kivy_image_picker(self, chosen_image: list, status_lbl: MDLabel) -> None:
        from kivy.uix.filechooser import FileChooserIconView

        picker = FileChooserIconView(
            path=str(Path.home()),
            filters=["*.png", "*.jpg", "*.jpeg"],
        )
        dialog: list = []

        def _select(*_):
            if picker.selection:
                dialog[0].dismiss()
                self._on_image_chosen(picker.selection, chosen_image, status_lbl)

        def _cancel(*_):
            dialog[0].dismiss()

        dlg = MDDialog(
            MDDialogHeadlineText(text="Select Thumbnail Image"),
            MDDialogContentContainer(picker),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text="Select"), style="filled", on_release=_select),
            ),
        )
        dialog.append(dlg)
        dlg.open()

    def _on_image_chosen(self, selection: list, chosen_image: list,
                          status_lbl: MDLabel) -> None:
        if selection and Path(selection[0]).is_file():
            chosen_image[0] = selection[0]
            status_lbl.text = Path(selection[0]).name

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _go_settings(self) -> None:
        app = MDApp.get_running_app()
        if app and app._sm:
            app._sm.current = "settings"

    def _open_docs(self) -> None:
        try:
            svc = self._host.get_service("docs_viewer")
            if svc:
                svc.open()
        except Exception as exc:
            self._host.log(f"[library] Could not open docs: {exc}")

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------

    def _toggle_search(self) -> None:
        self._search_visible = not self._search_visible
        if self._search_visible:
            self._search_field.height = dp(48)
            self._search_field.opacity = 1
            self._search_field.focus = True
        else:
            self._search_field.height = 0
            self._search_field.opacity = 0
            self._search_field.text = ""
            self._search_text = ""
            self.refresh()

    def _on_search(self, _instance, value: str) -> None:
        self._search_text = value
        self.refresh()

    # -----------------------------------------------------------------------
    # Snackbar
    # -----------------------------------------------------------------------

    def _show_snackbar(self, text: str) -> None:
        from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
        MDSnackbar(
            MDSnackbarText(text=text),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.8,
            duration=3,
        ).open()
