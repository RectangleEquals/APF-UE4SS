from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse
from kivy.metrics import dp
from kivy.properties import BooleanProperty
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton
from kivymd.uix.dialog import (
    MDDialog, MDDialogHeadlineText, MDDialogSupportingText,
    MDDialogContentContainer, MDDialogButtonContainer,
)
from kivymd.uix.label import MDLabel
from kivymd.uix.snackbar import MDSnackbar, MDSnackbarText
from kivymd.uix.textfield import MDTextField

from ..controllers import LibraryController
from .widgets import CarouselSection, AddGameTile, GameTile
from ....core.views.widgets.tip_icon_button import ImageIconButton
from ....core.controllers.logging.manager import APFLogManager

_log = APFLogManager.get_logger(__name__)

if TYPE_CHECKING:
    from ....core.controllers.plugin_host import PluginHost
    from ....core.models.config import APFConfig, GameProfile


_DISCORD_ICON = Path(__file__).parent.parent.parent.parent / "data" / "Discord_Symbol_White.png"


class _DotBadgeButton(MDBoxLayout):
    """MDIconButton wrapped in a layout that supports a red dot overlay badge."""

    has_badge = BooleanProperty(False)

    def __init__(self, icon: str, on_release=None, **kwargs):
        super().__init__(
            size_hint=(None, None), size=(dp(48), dp(48)), **kwargs
        )
        self._btn = MDIconButton(icon=icon, size_hint=(1, 1))
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


class LibraryScreen(MDBoxLayout):
    """
    Home screen — two labeled carousels: Steam and Custom Games.
    Folder-picker based Add Custom Game flow with UE root auto-detection.
    """

    def __init__(self, host: "PluginHost", config: "APFConfig", **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self._host = host
        self._config = config
        self._ctrl = LibraryController(host, config)
        self._search_visible: bool = False
        self._search_text: str = ""
        self._steam_games: list = []
        self._tile_map: dict[str, GameTile] = {}
        self._steam_section: Optional[CarouselSection] = None
        self._custom_section: Optional[CarouselSection] = None
        self._settings_badge_btn: Optional[_DotBadgeButton] = None
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
            discord_btn = ImageIconButton(
                source=str(_DISCORD_ICON), tooltip_text="Join our Discord")
            discord_btn.bind(on_release=lambda *_: webbrowser.open(
                "https://discord.gg/xhcVRhnjK"))
            toolbar.add_widget(discord_btn)
        self._settings_badge_btn = _DotBadgeButton(
            icon="cog", on_release=lambda *_: self._go_settings()
        )
        toolbar.add_widget(self._settings_badge_btn)
        self.add_widget(toolbar)

        self._search_field = MDTextField(
            hint_text="Search games…",
            mode="outlined",
            size_hint=(1, None),
            height=0,
            opacity=0,
        )
        self._search_field.bind(text=self._on_search)
        self.add_widget(self._search_field)

        outer_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self._sections_box = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
        )
        self._sections_box.bind(minimum_height=self._sections_box.setter("height"))

        self._steam_section = CarouselSection("Steam")
        self._custom_section = CarouselSection("Custom Games")
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
        if self._host.has_service("updates"):
            self._host.get_service("updates").check_all(
                on_done=self._apply_update_dot
            )
        # Subscribe so UE4SS badges update immediately after detection changes
        # (e.g. after installing UE4SS from the game hub content tab)
        if hasattr(self._host, "subscribe_state_change"):
            self._host.subscribe_state_change("detection", self._on_detection_changed)

    def _apply_update_dot(self) -> None:
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
        self._steam_section.clear_tiles()
        self._custom_section.clear_tiles()
        self._tile_map.clear()

        steam_games, custom_games = self._partition_games()

        for entry in steam_games:
            self._steam_section.add_tile(self._make_game_tile(entry))
        self._steam_section.opacity = 1

        self._custom_section.add_tile(AddGameTile(on_add=self._open_add_folder_picker))
        for entry in custom_games:
            self._custom_section.add_tile(self._make_game_tile(entry))

        if not self._search_text:
            self._steam_section.adjust_placeholders(len(steam_games))
            self._custom_section.adjust_placeholders(1 + len(custom_games))

    def _make_game_tile(self, profile: "GameProfile") -> GameTile:
        tile = GameTile(profile=profile, on_select=self._on_tile_selected)
        self._tile_map[profile.game_id] = tile
        if profile.steam_app_id:
            self._fetch_thumbnail(profile)
        threading.Thread(
            target=self._check_ue4ss_badge, args=(profile, tile), daemon=True,
        ).start()
        return tile

    def _partition_games(self) -> tuple[list, list]:
        from ....core.models.config import GameProfile

        config_games = list(self._config.games.values())
        config_app_ids = {p.steam_app_id for p in config_games if p.steam_app_id}

        config_steam = [g for g in config_games if g.steam_app_id]
        config_custom = [g for g in config_games if not g.steam_app_id]

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
        self._steam_games = self._ctrl.scan_steam_games()
        Clock.schedule_once(lambda dt: self.refresh(), 0)

    # -----------------------------------------------------------------------
    # Thumbnails
    # -----------------------------------------------------------------------

    def _fetch_thumbnail(self, profile: "GameProfile") -> None:
        if not profile.steam_app_id:
            return

        cached = self._ctrl.fetch_thumbnail(profile.steam_app_id, on_loaded=None)
        if cached:
            tile = self._tile_map.get(profile.game_id)
            if tile:
                tile._set_thumbnail(cached)
            return

        def _on_loaded(path):
            tile = self._tile_map.get(profile.game_id)
            if tile and path:
                Clock.schedule_once(lambda dt, p=path: tile._set_thumbnail(p), 0)

        self._ctrl.fetch_thumbnail(profile.steam_app_id, on_loaded=_on_loaded)

    # -----------------------------------------------------------------------
    # UE4SS badge
    # -----------------------------------------------------------------------

    def _check_ue4ss_badge(self, profile: "GameProfile", tile: GameTile) -> None:
        status = self._ctrl.get_ue4ss_badge_status(profile)
        Clock.schedule_once(lambda dt, s=status: tile.set_ue4ss_badge(s), 0)

    def _on_detection_changed(self) -> None:
        """Refresh UE4SS badges for all visible game tiles after a detection state change."""
        for game_id, tile in list(self._tile_map.items()):
            profile = self._config.games.get(game_id)
            if profile:
                threading.Thread(
                    target=self._check_ue4ss_badge, args=(profile, tile), daemon=True,
                ).start()

    # -----------------------------------------------------------------------
    # Tile click
    # -----------------------------------------------------------------------

    def _on_tile_selected(self, profile: "GameProfile") -> None:
        detection = self._ctrl.detect_game(profile.game_root)
        if detection.is_ue_game:
            self._ctrl.navigate_to_game(profile)
        else:
            MDSnackbar(MDSnackbarText(
                text="Not a UE game folder — check the game root path."
            )).open()

    def _confirm_remove_game(self, profile: "GameProfile") -> None:
        dialog: list = []

        def _do_remove(*_):
            self._ctrl.remove_game(profile)
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
            self._host.log(
                f"[library] tkinter folder picker failed: {type(exc).__name__}: {exc}")

        try:
            from plyer import filechooser
            filechooser.choose_dir(
                title="Select Game Folder",
                on_selection=self._on_dir_chosen,
            )
            return
        except Exception as exc:
            self._host.log(
                f"[library] plyer folder picker failed: {type(exc).__name__}: {exc}")

        self._host.log("[library] Falling back to Kivy folder picker.")
        self._open_kivy_folder_picker()

    def _open_kivy_folder_picker(self) -> None:
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
        game_root = self._ctrl.resolve_ue_root(selected)
        if game_root is None:
            self._show_snackbar("Not a recognized Unreal Engine game folder.")
            return

        existing_roots = {
            str(Path(p.game_root).resolve())
            for p in self._config.games.values()
            if p.game_root
        }
        if str(game_root.resolve()) in existing_roots:
            self._show_snackbar("This game is already in your library.")
            return

        self._open_add_details_dialog(game_root, self._ctrl.detect_game_name(game_root))

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
            name = name_field.text.strip() or auto_name
            self._ctrl.add_custom_game(game_root, name, chosen_image[0])
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
        except Exception as exc:
            _log.debug("[library] tkinter file picker unavailable, falling back to plyer: %s", exc)
        try:
            from plyer import filechooser
            filechooser.open_file(
                title="Select Thumbnail Image",
                filters=[("Image files", "*.png", "*.jpg", "*.jpeg")],
                on_selection=lambda sel: self._on_image_chosen(
                    sel, chosen_image, status_lbl),
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
        MDSnackbar(
            MDSnackbarText(text=text),
            y=dp(24),
            pos_hint={"center_x": 0.5},
            size_hint_x=0.8,
            duration=3,
        ).open()
