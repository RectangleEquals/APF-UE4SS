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
import os
import sys
from pathlib import Path


def main():
    # In frozen builds, point tkinter at the bundled tcl/tk script libraries.
    # _tkinter looks up TCL_LIBRARY/TK_LIBRARY at Tk() init time; the default
    # path still points to the original conda env after installation elsewhere.
    if getattr(sys, 'frozen', False):
        _exe_dir = Path(sys.executable).parent
        for _env, _subdir in (('TCL_LIBRARY', 'tcl8.6'), ('TK_LIBRARY', 'tk8.6')):
            _lib = _exe_dir / _subdir
            if _lib.exists():
                os.environ.setdefault(_env, str(_lib))

    # Strip app-specific flags from sys.argv BEFORE any Kivy import.
    # Kivy parses sys.argv at import time and errors on unrecognised flags.
    devtools_mode = "--devtools" in sys.argv
    if devtools_mode:
        sys.argv.remove("--devtools")

    # freeze_support() MUST be called before any Kivy import. The frozen
    # multiprocessing child process runs module-level code first; if Kivy is
    # imported at module level it initializes an SDL2 window before
    # freeze_support() can intercept and exit. Import APFManagerApp here so the
    # child process exits cleanly without ever touching Kivy.
    multiprocessing.freeze_support()
    from apf_manager.gui.app import APFManagerApp
    APFManagerApp(devtools_mode=devtools_mode).run()


if __name__ == "__main__":
    main()
