"""
cx_Freeze build script for APF Manager.

Usage:
    cd tools/apf_manager
    python setup.py build_exe

Prerequisites:
    plugins/docs_viewer/.github_token must exist (fine-grained PAT, contents:read).
    See Developer Setup in the plan for instructions.

Output: build/APFManager/
    APFManager.exe
    APFManagerDebug.exe
    python3xx.dll
    lib/
        library.zip       (cx_Freeze bundled modules)
        webview/          (pywebview package data — EdgeChromium backend helpers)
    plugins/
        ap_config/
        deploy/
        diagnostics/
        docs_viewer/
            assets/       (github-markdown-dark.css)
        html_viewer/
        library/
        manifesto/
        mods/
        packager/
        sessions/
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

# Add tools/ to sys.path so cx_Freeze can resolve 'apf_manager' as a package.
# apf_manager_entry.py uses 'from apf_manager.gui.app' (absolute, not relative).
# Without this, cx_Freeze cannot find tools/apf_manager/ as a named package.
sys.path.insert(0, str(HERE.parent))

# ---------------------------------------------------------------------------
# Build prerequisite checks
# ---------------------------------------------------------------------------

token_file = HERE / "plugins" / "docs_viewer" / ".github_token"
if "build_exe" in sys.argv and not token_file.exists():
    raise FileNotFoundError(
        f"Missing required build credential: {token_file}\n"
        "Create a fine-grained GitHub PAT (permissions: contents=read, repo: APF-UE4SS)\n"
        "and save the token (one line, no trailing newline) to that path."
    )

# ---------------------------------------------------------------------------
# Build options
# ---------------------------------------------------------------------------

EXCLUDES = [
    "tkinter",
    "unittest",
    # "email" — removed: needed by http.client for header parsing (urllib3 transitive dep)
    # "html"  — removed: needed by markdown.htmlparser (pure Python stdlib, NOT in python312.dll)
    # "http"  — removed: needed by requests/urllib3 for all network calls (pure Python stdlib)
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
    # Force-include entire apf_manager package — plugins are loaded dynamically
    # via importlib so cx_Freeze's static tracer misses modules only reachable
    # through plugin code (e.g. apf_manager.gui.theme).
    "apf_manager",
    "kivy",
    "kivymd",
    "requests",
    # HTML docs viewer (webview has dynamic backend loading; markdown auto-detects)
    # "webview" — NOT listed here; covered by INCLUDE_FILES + zip_exclude_packages.
    # Listing it here causes cx_Freeze to trace platform-specific backends (macOS/GTK/Qt)
    # and emit spurious "missing module" warnings for every non-Windows backend.
    # GitHub API client + HTTP (githubkit has dynamic model generation)
    "githubkit",
    "httpx",
    "httpx._transports",
]

INCLUDE_FILES = [
    # Kivy SDL2 DLLs are usually auto-detected, but list them explicitly
    # if needed on the target machine. Add paths as required.
]

# pywebview — bundle EdgeChromium backend helpers into build/APFManager/lib/webview/
try:
    import webview as _wv
    _wv_dir = Path(_wv.__file__).parent
    if _wv_dir.exists():
        INCLUDE_FILES.append((str(_wv_dir), "lib/webview"))
except ImportError:
    pass  # Not installed yet; will fail at runtime, but won't break the build script

# Kivy data files — GLSL shaders, fonts, atlas images (accessed via __file__ paths)
try:
    import kivy as _kv
    _kv_data = Path(_kv.__file__).parent / 'data'
    if _kv_data.exists():
        INCLUDE_FILES.append((str(_kv_data), 'lib/kivy/data'))
except ImportError:
    pass

# KivyMD font/image data — Material Design icon fonts and logo images
try:
    import kivymd as _kvmd
    _kvmd_dir = Path(_kvmd.__file__).parent
    for _subdir in ('fonts', 'images'):
        _p = _kvmd_dir / _subdir
        if _p.exists():
            INCLUDE_FILES.append((str(_p), f'lib/kivymd/{_subdir}'))
except ImportError:
    pass

# Markdown — copy full source package to lib/markdown/
# cx_Freeze's static tracer partially traces markdown (finds __init__ but misses internal
# relative imports like `from .core import Markdown`). Copying the full source tree ensures
# all submodules (core, preprocessors, extensions, etc.) are present as .py source files
# in lib/markdown/. Python's standard PathFinder resolves .py files in real lib/ directories.
try:
    import markdown as _md_pkg
    _md_dir = Path(_md_pkg.__file__).parent
    if _md_dir.exists():
        INCLUDE_FILES.append((str(_md_dir), 'lib/markdown'))
except ImportError:
    if "build_exe" in sys.argv:
        raise RuntimeError(
            "Package 'markdown' not found in build environment. "
            "Install it: pip install markdown>=3.5"
        )

# clr_loader — copy full package to lib/clr_loader/ (includes native ClrLoader.dll)
# clr_loader.ffi.load_netfx() computes: Path(__file__).parent / "dlls" / "amd64" / "ClrLoader.dll"
# If clr_loader is in library.zip, __file__ is a virtual zip path → LoadLibrary fails (error 0x7e).
# Copying full source + DLL to lib/ ensures __file__ is a real path and the DLL is findable.
try:
    import clr_loader as _clr_loader_pkg
    _clr_loader_dir = Path(_clr_loader_pkg.__file__).parent
    if _clr_loader_dir.exists():
        INCLUDE_FILES.append((str(_clr_loader_dir), 'lib/clr_loader'))
except ImportError:
    pass

# pythonnet — copy full package to lib/pythonnet/ (includes Python.Runtime.dll)
# pythonnet.__init__.load() computes: Path(__file__).parent / "runtime" / "Python.Runtime.dll"
# Same zip-path problem applies — must be at a real disk path.
try:
    import pythonnet as _pythonnet_pkg
    _pythonnet_dir = Path(_pythonnet_pkg.__file__).parent
    if _pythonnet_dir.exists():
        INCLUDE_FILES.append((str(_pythonnet_dir), 'lib/pythonnet'))
except ImportError:
    pass

# SDL DLLs — bundle all SDL generations at the exe root for consistency.
# SDL3: KivyMD master loads dynamically; never auto-detected by cx_Freeze — must be explicit.
# SDL2: cx_Freeze auto-detects these (via _window_sdl2.pyd) and places them in lib/;
#   duplicating at root consolidates all SDL binaries in one place. Harmless duplicate.
_conda_bin = Path(sys.executable).parent / 'Library' / 'bin'
for _dll in ('SDL2.dll', 'SDL2_image.dll', 'SDL2_mixer.dll', 'SDL2_ttf.dll', 'SDL3.dll'):
    _p = _conda_bin / _dll
    if _p.exists():
        INCLUDE_FILES.append((str(_p), _dll))


build_options = {
    "packages": PACKAGES,
    "excludes": EXCLUDES,
    "include_files": INCLUDE_FILES,
    "zip_include_packages": ["*"],
    "zip_exclude_packages": ["kivy", "kivymd", "markdown", "clr_loader", "pythonnet", "webview"],
    "include_msvcr": True,
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
        script=str(HERE / "apf_manager_entry.py"),
        target_name="APFManager.exe",
        base=gui_base,
        icon=str(HERE / "data" / "icon.ico") if (HERE / "data" / "icon.ico").exists() else None,
    ),
    Executable(
        script=str(HERE / "apf_manager_entry.py"),
        target_name="APFManagerDebug.exe",
        base=console_base,
        icon=str(HERE / "data" / "icon.ico") if (HERE / "data" / "icon.ico").exists() else None,
    ),
]

# ---------------------------------------------------------------------------
# Post-build hook: copy plugins/ and data/ into build output
# ---------------------------------------------------------------------------

def _post_build():
    build_dir = Path(build_options["build_exe"])
    if not build_dir.exists():
        return

    # Copy built-in plugins → build/APFManager/plugins/
    # Includes: docs_viewer/assets/, html_viewer/, docs_viewer/.github_token
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
