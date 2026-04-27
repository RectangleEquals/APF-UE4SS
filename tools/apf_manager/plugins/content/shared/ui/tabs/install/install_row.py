"""install_row.py — re-export shim (superseded by InstalledRowWidget).

The hand-built row builders that lived here have been replaced by the typed
InstalledRowWidget in shared/ui/installed_row_widget.py.  This module is kept
as a thin shim so any external reference to _BG_ROW_AP remains importable.
"""

_BG_ROW_AP = (0.13, 0.14, 0.15, 1)
