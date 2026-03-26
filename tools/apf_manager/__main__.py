"""
APF Manager — entry point.

Run in development:
    python -m tools.apf_manager

Frozen (cx_Freeze):
    APFManager.exe
"""

import multiprocessing

from .gui.app import APFManagerApp


def main():
    # Required for cx_Freeze + multiprocessing (no-op in dev).
    # Must be called before APFManagerApp().run() so that frozen builds can
    # intercept multiprocessing respawn (e.g. html_viewer subprocess) before
    # the Kivy app loop starts.
    multiprocessing.freeze_support()
    APFManagerApp().run()


if __name__ == "__main__":
    main()
