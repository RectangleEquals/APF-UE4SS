"""
APF Manager — entry point.

Run in development:
    python -m tools.apf_manager

Frozen (cx_Freeze):
    APFManager.exe
"""

from .gui.app import APFManagerApp


def main():
    APFManagerApp().run()


if __name__ == "__main__":
    main()
