"""
main.py -- APF Manifesto entry point.

Run with:  python main.py
Build with: .\build.ps1 (PyInstaller)

Import order matters:
  1. kivy.config  (before any other kivy import)
  2. app.ui.app   (triggers KivyMD factory registration for all widgets)
  3. ManifestoApp().run()
"""
import os
import sys
from pathlib import Path

# -- PyInstaller resource path fix -------------------------------------------
if getattr(sys, "frozen", False):
    _base = Path(sys._MEIPASS)
    os.environ["KIVY_HOME"] = str(_base / "kivy_home")
    os.environ.setdefault("KIVY_DATA_DIR", str(_base / "kivy" / "data"))

# -- Kivy window config (must come before ANY kivy import) -------------------
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")
from kivy.config import Config                       # noqa: E402
Config.set("graphics", "width",           "1280")
Config.set("graphics", "height",          "800")
Config.set("graphics", "minimum_width",   "1100")
Config.set("graphics", "minimum_height",  "700")
Config.set("input", "mouse", "mouse,multitouch_on_demand")

# -- Import app (pre-registers all KivyMD widgets) ---------------------------
from app.ui.app import ManifestoApp                  # noqa: E402

if __name__ == "__main__":
    ManifestoApp().run()
