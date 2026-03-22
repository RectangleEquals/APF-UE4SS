"""
LibraryScreen — game library home screen.

Phase 1: Reads GameProfile entries from APFConfig and renders them as tiles.
         Gradient placeholder tiles; custom_thumbnail shown if set.
Phase 2: Adds Steam VDF/ACF scanning + async thumbnail enrichment (see plan).
"""

from __future__ import annotations

import hashlib
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
# Tile color palette — deterministic from game display_name hash
# ---------------------------------------------------------------------------

_TILE_COLORS = [
    (0.18, 0.28, 0.42, 1),  # deep blue
    (0.22, 0.35, 0.28, 1),  # deep green
    (0.38, 0.22, 0.22, 1),  # deep red
    (0.32, 0.28, 0.18, 1),  # deep amber
    (0.28, 0.22, 0.38, 1),  # deep purple
    (0.18, 0.35, 0.38, 1),  # deep teal
    (0.38, 0.28, 0.18, 1),  # deep orange
    (0.22, 0.22, 0.38, 1),  # deep indigo
]


def _tile_color(name: str) -> tuple:
    idx = int(hashlib.md5(name.encode()).hexdigest(), 16) % len(_TILE_COLORS)
    return _TILE_COLORS[idx]


# ---------------------------------------------------------------------------
# GameTile
# ---------------------------------------------------------------------------

class GameTile(MDCard):
    """Single game tile in the library grid."""

    def __init__(self, profile: "GameProfile", on_select, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint=(None, None),
            size=(dp(180), dp(160)),
            ripple_behavior=True,
            md_bg_color=(0.12, 0.12, 0.12, 1),
            **kwargs,
        )
        self._profile = profile
        self._on_select = on_select
        self._bg_rect: Optional[Rectangle] = None
        self._build()

    def _build(self) -> None:
        color = _tile_color(self._profile.display_name)
        with self.canvas.before:
            Color(*color)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_bg, size=self._update_bg)

        # Thumbnail or placeholder
        thumb = self._profile.custom_thumbnail
        if thumb and Path(thumb).exists():
            from kivy.uix.image import Image
            self.add_widget(Image(
                source=thumb,
                allow_stretch=True,
                keep_ratio=False,
                size_hint=(1, 0.75),
            ))
        else:
            self.add_widget(MDLabel(
                text="?",
                font_style="H2",
                halign="center",
                valign="middle",
                size_hint=(1, 0.75),
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.2),
            ))

        # Name bar
        name_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint=(1, 0.25),
            padding=[dp(8), dp(4)],
            md_bg_color=(0, 0, 0, 0.6),
        )
        name_bar.add_widget(MDLabel(
            text=self._profile.display_name,
            font_style="Caption",
            halign="left",
            valign="middle",
            shorten=True,
            shorten_from="right",
            size_hint=(1, 1),
            theme_text_color="Custom",
            text_color=(1, 1, 1, 0.9),
        ))
        self.add_widget(name_bar)

        self.bind(on_release=lambda *_: self._on_select(self._profile))

    def _update_bg(self, *_) -> None:
        if self._bg_rect:
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size


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
    Home screen widget — shows configured games as a tile grid.
    Passed to APFManagerApp as the home_screen contribution panel.
    """

    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._config = config
        self._add_dialog: Optional[MDDialog] = None
        self._ue4ss_dialog: Optional[MDDialog] = None
        self._search_visible: bool = False
        self._search_text: str = ""
        self._build()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self) -> None:
        # Top bar
        self._toolbar = MDTopAppBar(
            title="Game Library",
            elevation=0,
            right_action_items=[
                ["magnify", lambda x: self._toggle_search()],
                ["plus", lambda x: self._open_add_dialog()],
                ["cog", lambda x: self._go_settings()],
            ],
        )
        self.add_widget(self._toolbar)

        # Collapsible search bar
        self._search_field = MDTextField(
            hint_text="Search games…",
            mode="rectangle",
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

        Clock.schedule_once(lambda dt: self.refresh(), 0)

    # -----------------------------------------------------------------------
    # Public
    # -----------------------------------------------------------------------

    def refresh(self) -> None:
        """Rebuild the tile grid from the current config."""
        self._grid.clear_widgets()
        games = list(self._config.games.values())

        if self._search_text:
            q = self._search_text.lower()
            games = [g for g in games if q in g.display_name.lower()]

        if not games:
            self._grid.add_widget(MDLabel(
                text="No games added.\nPress + to add a game.",
                halign="center",
                valign="middle",
                size_hint=(1, None),
                height=dp(140),
            ))
            return

        for profile in games:
            self._grid.add_widget(
                GameTile(profile=profile, on_select=self._on_tile_selected)
            )

    # -----------------------------------------------------------------------
    # Tile click
    # -----------------------------------------------------------------------

    def _on_tile_selected(self, profile: "GameProfile") -> None:
        from ...core.ue4ss import UE4SSDetector
        detection = UE4SSDetector.detect(profile.game_root)
        if detection.valid:
            self._host.navigate_to_game(profile)
        else:
            self._show_ue4ss_dialog(profile, detection)

    # -----------------------------------------------------------------------
    # UE4SS missing dialog
    # -----------------------------------------------------------------------

    def _show_ue4ss_dialog(self, profile: "GameProfile", detection) -> None:
        if detection.missing:
            missing_str = ", ".join(detection.missing)
            detail = f"Missing: {missing_str}"
        else:
            detail = "Could not locate UE4SS in the game folder."

        def _dismiss(*_):
            if self._ue4ss_dialog:
                self._ue4ss_dialog.dismiss()

        def _download(*_):
            webbrowser.open(
                "https://github.com/UE4SS-RE/RE-UE4SS/releases/latest"
            )
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
    # Navigation helpers
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
