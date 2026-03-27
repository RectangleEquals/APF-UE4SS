"""
Frozen entry point for cx_Freeze.

cx_Freeze processes __main__.py as a standalone entry script with no package
context, so the relative import 'from .gui.app import APFManagerApp' cannot be
resolved — gui.app and all its dependencies are NOT bundled.

This wrapper uses absolute imports so cx_Freeze can trace and bundle the full
apf_manager package. setup.py adds tools/ to sys.path so 'apf_manager' is
importable during the build.

Development entry: python -m tools.apf_manager  (uses __main__.py)
Frozen entry:      APFManager.exe / APFManagerDebug.exe  (uses this file)
"""
import multiprocessing

from apf_manager.gui.app import APFManagerApp


def main():
    # Required for cx_Freeze + multiprocessing (no-op in dev).
    # Must be called before APFManagerApp().run() so that frozen builds can
    # intercept multiprocessing respawn (e.g. html_viewer subprocess) before
    # the Kivy app loop starts.
    multiprocessing.freeze_support()
    APFManagerApp().run()


if __name__ == "__main__":
    main()
