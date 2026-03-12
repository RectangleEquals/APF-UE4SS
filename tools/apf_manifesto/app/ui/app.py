"""
ui/app.py
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

# -- Pre-register all KivyMD widgets so Kivy's factory is populated ----------
from kivymd.uix.toolbar import MDTopAppBar          # noqa: F401
from kivymd.uix.boxlayout import MDBoxLayout        # noqa: F401
from kivymd.uix.floatlayout import MDFloatLayout    # noqa: F401
from kivymd.uix.scrollview import MDScrollView      # noqa: F401
from kivymd.uix.label import MDLabel                # noqa: F401
from kivymd.uix.button import (                     # noqa: F401
    MDFlatButton, MDRaisedButton, MDIconButton,
)
from kivymd.uix.textfield import MDTextField        # noqa: F401
from kivymd.uix.card import MDCard                  # noqa: F401
from kivymd.uix.dialog import MDDialog              # noqa: F401
from kivymd.uix.tab import MDTabs, MDTabsBase       # noqa: F401
from kivymd.uix.list import (                       # noqa: F401
    MDList, TwoLineIconListItem, OneLineListItem,
    TwoLineListItem, IconLeftWidget,
)
from kivymd.uix.selectioncontrol import MDCheckbox  # noqa: F401
from kivymd.uix.snackbar import MDSnackbar          # noqa: F401

from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivymd.app import MDApp

from ..core.mod_registry import ModRegistry


def _mods_dir() -> str:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent.parent
    mods = base / "Mods"
    mods.mkdir(parents=True, exist_ok=True)
    return str(mods)



class ManifestoApp(MDApp):
    title = "APF Manifesto"
    registry: ModRegistry = None

    def build(self):
        self.theme_cls.primary_palette = "BlueGray"
        self.theme_cls.accent_palette  = "Amber"
        self.theme_cls.theme_style     = "Dark"

        Window.minimum_width  = 1100
        Window.minimum_height = 700
        Window.size = (1280, 800)

        self.registry = ModRegistry(_mods_dir())
        self.registry.scan()

        sm = ScreenManager(transition=FadeTransition(duration=0.15))
        from .screens.home_screen import HomeScreen
        sm.add_widget(HomeScreen(name="home"))
        return sm

    # ------------------------------------------------------------------

    def open_mod(self, manifest_path: str, read_only: bool = False) -> None:
        from ..core.manifest_io import load_manifest
        from .screens.editor_screen import EditorScreen
        try:
            model = load_manifest(manifest_path)
        except Exception:
            self._show_error(f"Failed to load manifest:\n{traceback.format_exc()}")
            return

        sm = self.root
        screen_name = f"editor_{model.mod_id}"
        if sm.has_screen(screen_name):
            sm.current = screen_name
            return

        model._read_only = read_only
        try:
            editor = EditorScreen(
                name=screen_name,
                model=model,
                registry=self.registry,
            )
        except Exception:
            self._show_error(f"Failed to create editor:\n{traceback.format_exc()}")
            return

        sm.add_widget(editor)
        sm.current = screen_name

    def go_home(self) -> None:
        self.root.current = "home"


    def _show_error(self, msg: str) -> None:
        """
        Error dialog with scrollable text and Copy button.

        MDDialog type='custom' uses content_cls.height to size itself, so the
        content widget MUST have size_hint_y=None and a fixed height — a widget
        with size_hint=(1,1) reports height=100 at schedule time and the dialog
        renders blank.
        """
        from kivy.core.clipboard import Clipboard
        from kivy.uix.boxlayout import BoxLayout

        # Fixed-height container so MDDialog.update_height() gets a real value
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height="320dp",
            padding=("0dp", "4dp"),
        )

        from kivy.uix.scrollview import ScrollView
        scroll = ScrollView(size_hint=(1, 1))
        lbl = MDLabel(
            text=msg,
            theme_text_color="Secondary",
            size_hint_y=None,
            halign="left",
            valign="top",
        )
        lbl.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))
        scroll.add_widget(lbl)
        content.add_widget(scroll)

        copied_lbl = MDLabel(
            text="",
            theme_text_color="Hint",
            size_hint_y=None,
            height="24dp",
            halign="center",
        )
        content.add_widget(copied_lbl)

        dlg = [None]

        def _copy(*_):
            Clipboard.copy(msg)
            copied_lbl.text = "\u2713 Copied to clipboard"

        dlg[0] = MDDialog(
            title="Error",
            type="custom",
            content_cls=content,
            buttons=[
                MDFlatButton(text="COPY", on_release=_copy),
                MDRaisedButton(text="OK",
                               on_release=lambda *_: dlg[0].dismiss()),
            ],
        )
        dlg[0].open()

