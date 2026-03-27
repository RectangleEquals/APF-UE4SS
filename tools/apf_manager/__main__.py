"""
APF Manager — entry point.

Run in development:
    python -m tools.apf_manager

Frozen (cx_Freeze):
    APFManager.exe
"""

import multiprocessing


def main():
    # freeze_support() MUST be called before any Kivy import. The frozen
    # multiprocessing child process runs module-level code first; if Kivy is
    # imported at module level it initializes an SDL2 window before
    # freeze_support() can intercept and exit. Import APFManagerApp here so the
    # child process exits cleanly without ever touching Kivy.
    multiprocessing.freeze_support()
    from .gui.app import APFManagerApp
    APFManagerApp().run()


if __name__ == "__main__":
    main()
