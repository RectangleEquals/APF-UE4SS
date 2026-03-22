"""
cx_Freeze build script for APF Manager.

Usage:
    cd tools/apf_manager
    python setup.py build_exe

Output: build/exe.win-amd64-3.x/
    APFManager.exe
    APFManagerDebug.exe
    python3xx.dll
    lib/
        library.zip       (cx_Freeze bundled modules)
    plugins/              (built-in plugin sources, copied post-build)
    custom_plugins/       (empty — user drops .apfplugin files here)
    data/                 (icons, theme assets)

Mirrors Archipelago's setup.py structure.
"""

import os
import shutil
import sys
from pathlib import Path

import cx_Freeze
from cx_Freeze import setup, Executable

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HERE = Path(__file__).parent
ROOT = HERE.parent.parent  # ipc_2/

# ---------------------------------------------------------------------------
# Build options
# ---------------------------------------------------------------------------

EXCLUDES = [
    "tkinter",
    "unittest",
    "email",
    "html",
    "http",
    "xmlrpc",
    "distutils",
    "test",
    "pydoc",
    "doctest",
    "difflib",
    "ftplib",
    "imaplib",
    "poplib",
    "smtplib",
    "telnetlib",
]

PACKAGES = [
    "kivy",
    "kivymd",
    "requests",
]

INCLUDE_FILES = [
    # Kivy SDL2 DLLs are usually auto-detected, but list them explicitly
    # if needed on the target machine. Add paths as required.
]

build_options = {
    "packages": PACKAGES,
    "excludes": EXCLUDES,
    "include_files": INCLUDE_FILES,
    "zip_include_packages": ["*"],
    "zip_exclude_packages": [],
    "silent": True,
    "build_exe": str(HERE / "build" / "APFManager"),
}

# ---------------------------------------------------------------------------
# Executables
# ---------------------------------------------------------------------------

gui_base = "Win32GUI" if sys.platform == "win32" else None
console_base = "Console"

executables = [
    Executable(
        script=str(HERE / "__main__.py"),
        target_name="APFManager.exe",
        base=gui_base,
        icon=str(HERE / "data" / "icon.ico") if (HERE / "data" / "icon.ico").exists() else None,
    ),
    Executable(
        script=str(HERE / "__main__.py"),
        target_name="APFManagerDebug.exe",
        base=console_base,
        icon=str(HERE / "data" / "icon.ico") if (HERE / "data" / "icon.ico").exists() else None,
    ),
]

# ---------------------------------------------------------------------------
# Post-build hook: copy plugins/ and data/ into build output
# ---------------------------------------------------------------------------

class _PostBuild(cx_Freeze.hooks.Module):
    pass


def _post_build():
    build_dir = Path(build_options["build_exe"])
    if not build_dir.exists():
        return

    # Copy built-in plugins → build/APFManager/plugins/
    plugins_dst = build_dir / "plugins"
    plugins_src = HERE / "plugins"
    if plugins_dst.exists():
        shutil.rmtree(plugins_dst)
    shutil.copytree(plugins_src, plugins_dst)
    print(f"Copied plugins/ → {plugins_dst}")

    # Create empty custom_plugins/
    custom = build_dir / "custom_plugins"
    custom.mkdir(exist_ok=True)
    print(f"Created custom_plugins/ → {custom}")

    # Copy data/ if present
    data_src = HERE / "data"
    if data_src.is_dir():
        data_dst = build_dir / "data"
        if data_dst.exists():
            shutil.rmtree(data_dst)
        shutil.copytree(data_src, data_dst)
        print(f"Copied data/ → {data_dst}")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

setup(
    name="APFManager",
    version="1.0.0",
    description="AP Framework Manager",
    options={"build_exe": build_options},
    executables=executables,
)

# Run post-build steps (only when actually building)
if "build_exe" in sys.argv:
    _post_build()
