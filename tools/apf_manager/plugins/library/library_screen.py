"""
LibraryScreen — game library home screen.

Phase 1: Shows GameProfile entries from APFConfig as tiles (gradient placeholders).
Phase 2: Adds Steam VDF/ACF scanning, UE filter, async thumbnails, UE4SS badges.
"""

from __future__ import annotations

import hashlib
import threading
import webbrowser
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogContentContainer, MDDialogButtonContainer,
)
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.textfield import MDTextField
from kivymd.uix.toolbar import MDTopAppBar

if TYPE_CHECKING:
    from ...core.plugin_host import PluginHost
    from ...core.config import APFConfig, GameProfile


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


# UE4SS badge colours: green=installed, yellow=undetected, red=missing game root
_BADGE_COLORS = {
    "ok":      (0.3, 0.8, 0.4, 1),
    "warn":    (0.9, 0.7, 0.1, 1),
    "error":   (0.85, 0.25, 0.25, 1),
    "unknown": (0.5, 0.5, 0.5, 1),
}


# ---------------------------------------------------------------------------
# GameTile
# ---------------------------------------------------------------------------

class GameTile(MDCard):
    """Single game tile in the library grid."""

    def __init__(self, profile: "GameProfile", on_select, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(dp(200), dp(150)),
            md_bg_color=(0.12, 0.12, 0.12, 1),
            **kwargs,
        )
        self._profile = profile
        self._on_select = on_select
        self._bg_rect: Optional[Rectangle] = None
        self._thumb_widget = None
        self._badge_lbl: Optional[MDLabel] = None
        self._build()

    def _build(self) -> None:
        color = _tile_color(self._profile.display_name)
        with self.canvas.before:
            Color(*color)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # Image area (thumbnail or "?" placeholder)
        self._img_area = MDBoxLayout(size_hint=(1, 0.72), orientation="vertical")
        thumb = self._profile.custom_thumbnail
        if thumb and Path(thumb).exists():
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

        # Name bar
        name_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, 0.20),
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

        # UE4SS badge (bottom-right corner overlay)
        badge_row = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, 0.08),
            padding=[0, 0, dp(4), 0],
        )
        self._badge_lbl = MDLabel(
            text="UE4SS ?",
            font_style="Label",
            role="small",
            halign="right",
            valign="middle",
            theme_text_color="Custom",
            text_color=_BADGE_COLORS["unknown"],
        )
        badge_row.add_widget(self._badge_lbl)
        self.add_widget(badge_row)

        self.bind(on_release=lambda *_: self._on_select(self._profile))

    def _update_bg(self, *_) -> None:
        if self._bg_rect:
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size

    def set_thumbnail(self, path: Path) -> None:
        """Called from background thread via Clock.schedule_once."""
        Clock.schedule_once(lambda dt: self._set_thumbnail(path), 0)

    def _set_thumbnail(self, path: Path) -> None:
        from kivy.uix.image import Image
        self._img_area.clear_widgets()
        self._img_area.add_widget(Image(
            source=str(path),
            allow_stretch=True,
            keep_ratio=False,
        ))

    def set_ue4ss_badge(self, status: str) -> None:
        """status: 'ok' | 'warn' | 'error' | 'unknown'"""
        if self._badge_lbl is None:
            return
        labels = {"ok": "UE4SS ✓", "warn": "UE4SS !", "error": "UE4SS ✗", "unknown": "UE4SS ?"}
        self._badge_lbl.text = labels.get(status, "UE4SS ?")
        self._badge_lbl.text_color = _BADGE_COLORS.get(status, _BADGE_COLORS["unknown"])


# ---------------------------------------------------------------------------
# Add Custom Game — dialog content
# ---------------------------------------------------------------------------

class _AddGameContent(MDBoxLayout):
    def __init__(self, **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=dp(8),
            padding=[dp(4), dp(8)],
            size_hint_y=None,
            **kwargs,
        )
        self.height = dp(130)

        self.name_field = MDTextField(hint_text="Game name", mode="outlined")
        self.path_field = MDTextField(
            hint_text="Game root folder (absolute path)", mode="outlined"
        )
        self.add_widget(self.name_field)
        self.add_widget(self.path_field)


# ---------------------------------------------------------------------------
# LibraryScreen
# ---------------------------------------------------------------------------

class LibraryScreen(MDBoxLayout):
    """
    Home screen — tile grid of all games.
    Phase 1: config-only GameProfiles.
    Phase 2: + Steam-discovered games (UE-filtered) with async thumbnails.
    """

    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._config = config
        self._add_dialog: Optional[MDDialog] = None
        self._ue4ss_dialog: Optional[MDDialog] = None
        self._search_visible: bool = False
        self._search_text: str = ""
        self._steam_games: list = []          # list[SteamGame] — refreshed on build
        self._thumbnail_cache = None          # ThumbnailCache — lazily created
        self._tile_map: dict[str, "GameTile"] = {}  # game_id/str(app_id) → tile
        self._build()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        self._toolbar = MDTopAppBar(
            title="Game Library",
            elevation=0,
            right_action_items=[
                ["magnify", lambda x: self._toggle_search()],
                ["refresh", lambda x: threading.Thread(
                    target=self._refresh_steam, daemon=True).start()],
                ["plus", lambda x: self._open_add_dialog()],
                ["cog", lambda x: self._go_settings()],
            ],
        )
        self.add_widget(self._toolbar)

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

        # Scrollable tile grid
        scroll = ScrollView(size_hint=(1, 1))
        self._grid = MDGridLayout(
            cols=4,
            spacing=dp(12),
            padding=[dp(16), dp(16)],
            size_hint_y=None,
            adaptive_height=True,
        )
        scroll.add_widget(self._grid)
        self.add_widget(scroll)

        Clock.schedule_once(lambda dt: self._initial_load(), 0)

    # -----------------------------------------------------------------------
    # Load
    # -----------------------------------------------------------------------

    def _initial_load(self) -> None:
        """Populate from config first (instant), then scan Steam in background."""
        self.refresh()
        threading.Thread(target=self._refresh_steam, daemon=True).start()

    # -----------------------------------------------------------------------
    # Public
    # -----------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild tile grid from config + cached steam games."""
        self._grid.clear_widgets()
        self._tile_map.clear()
        games = self._build_game_list()

        if not games:
            self._grid.add_widget(MDLabel(
                text="No games found.\nPress the Steam icon to scan, or + to add manually.",
                halign="center",
                valign="middle",
                size_hint=(1, None),
                height=dp(120),
            ))
            return

        for entry in games:
            tile = GameTile(
                profile=entry,
                on_select=self._on_tile_selected,
            )
            key = entry.game_id
            self._tile_map[key] = tile
            self._grid.add_widget(tile)

            # Async thumbnail for Steam games
            if entry.steam_app_id and self._get_thumbnail_cache():
                self._fetch_thumbnail(entry)

            # Async UE4SS badge check
            threading.Thread(
                target=self._check_ue4ss_badge,
                args=(entry, tile),
                daemon=True,
            ).start()

    def _build_game_list(self) -> list["GameProfile"]:
        """
        Merge config games + Steam-discovered games.
        Config games take precedence (steam_app_id used for dedup).
        Applies search filter.
        """
        from ...core.config import GameProfile

        # Start with config profiles
        result: list[GameProfile] = list(self._config.games.values())
        config_app_ids = {p.steam_app_id for p in result if p.steam_app_id}

        # Add Steam-discovered games not already in config
        for sg in self._steam_games:
            if sg.app_id not in config_app_ids:
                profile = GameProfile.new(
                    display_name=sg.name,
                    game_root=str(sg.install_dir),
                    steam_app_id=sg.app_id,
                )
                result.append(profile)

        # Search filter
        if self._search_text:
            q = self._search_text.lower()
            result = [g for g in result if q in g.display_name.lower()]

        return result

    # -----------------------------------------------------------------------
    # Steam scan
    # -----------------------------------------------------------------------

    def _refresh_steam(self) -> None:
        """Background: scan Steam library, update tile grid on main thread."""
        try:
            from .steam_library import SteamLibrary, UEFilter
            override = self._config.steam_library_override
            lib = SteamLibrary(override_vdf_path=override)
            all_games = lib.scan()
            # Filter to UE games only
            ue_games = [g for g in all_games if g.is_ue]
            self._steam_games = ue_games
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

    def _check_ue4ss_badge(self, profile: "GameProfile", tile: "GameTile") -> None:
        from ...core.ue4ss import UE4SSDetector
        if not profile.game_root:
            status = "unknown"
        elif not Path(profile.game_root).is_dir():
            status = "error"
        else:
            detection = UE4SSDetector.detect(profile.game_root)
            status = "ok" if detection.valid else "warn"
        Clock.schedule_once(lambda dt, s=status: tile.set_ue4ss_badge(s), 0)

    # -----------------------------------------------------------------------
    # Tile click
    # -----------------------------------------------------------------------

    def _on_tile_selected(self, profile: "GameProfile") -> None:
        from ...core.ue4ss import UE4SSDetector
        detection = UE4SSDetector.detect(profile.game_root)
        if detection.valid:
            # Ensure profile is in config before navigating
            if profile.game_id not in self._config.games:
                self._config.add_game(profile)
            self._host.navigate_to_game(profile)
        else:
            self._show_ue4ss_dialog(profile, detection)

    # -----------------------------------------------------------------------
    # UE4SS missing dialog
    # -----------------------------------------------------------------------

    def _show_ue4ss_dialog(self, profile: "GameProfile", detection) -> None:
        if detection.missing:
            detail = "Missing: " + ", ".join(detection.missing)
        else:
            detail = "Could not locate UE4SS in the game folder."

        def _dismiss(*_):
            if self._ue4ss_dialog:
                self._ue4ss_dialog.dismiss()

        def _download(*_):
            webbrowser.open("https://github.com/UE4SS-RE/RE-UE4SS/releases/latest")
            _dismiss()

        self._ue4ss_dialog = MDDialog(
            MDDialogHeadlineText(text="UE4SS Not Detected"),
            MDDialogSupportingText(text=(
                f"UE4SS was not found for {profile.display_name}.\n\n"
                f"{detail}\n\n"
                "Install UE4SS into the game's Binaries/Win64/ folder, "
                "then try again."
            )),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_dismiss),
                MDButton(MDButtonText(text="Download UE4SS"), style="filled", on_release=_download),
            ),
        )
        self._ue4ss_dialog.open()

    # -----------------------------------------------------------------------
    # Add Custom Game dialog
    # -----------------------------------------------------------------------

    def _open_add_dialog(self) -> None:
        content = _AddGameContent()

        def _confirm(*_):
            name = content.name_field.text.strip()
            path = content.path_field.text.strip()
            if name and path:
                from ...core.config import GameProfile
                self._config.add_game(GameProfile.new(
                    display_name=name, game_root=path
                ))
                self.refresh()
            if self._add_dialog:
                self._add_dialog.dismiss()

        def _cancel(*_):
            if self._add_dialog:
                self._add_dialog.dismiss()

        self._add_dialog = MDDialog(
            MDDialogHeadlineText(text="Add Custom Game"),
            MDDialogContentContainer(content),
            MDDialogButtonContainer(
                Widget(),
                MDButton(MDButtonText(text="Cancel"), style="text", on_release=_cancel),
                MDButton(MDButtonText(text="Add"), style="filled", on_release=_confirm),
            ),
        )
        self._add_dialog.open()

    # -----------------------------------------------------------------------
    # Navigation
    # -----------------------------------------------------------------------

    def _go_settings(self) -> None:
        app = MDApp.get_running_app()
        if app and app._sm:
            app._sm.current = "settings"

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