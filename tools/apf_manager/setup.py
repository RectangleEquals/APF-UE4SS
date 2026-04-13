"""
cx_Freeze build script for APF Manager.

Usage:
    cd tools/apf_manager
    python setup.py build_exe

Prerequisites:
    data/.github_token must exist (fine-grained PAT, contents:read).
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
# Manager version — read from __version__.py (the only file to edit when bumping)
# ---------------------------------------------------------------------------

try:
    _ver_ns: dict = {}
    exec((HERE / "__version__.py").read_text(encoding="utf-8"), _ver_ns)
    _MANAGER_VERSION: str = _ver_ns.get("__version__", "0.0.0")
except FileNotFoundError:
    print(
        "Warning: tools/apf_manager/__version__.py not found. "
        "Using version 0.0.0. Create this file before a real release build."
    )
    _MANAGER_VERSION = "0.0.0"

# ---------------------------------------------------------------------------
# Build prerequisite checks
# ---------------------------------------------------------------------------

token_file = HERE / "data" / ".github_token"
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
    # tkinter intentionally NOT excluded — the folder picker in library_screen.py
    # uses tkinter.filedialog.askdirectory() as its primary (native) dialog.
    # Excluding it forces a fallback to the Kivy FileChooser which returns unexpected
    # path formats on fresh installs (Bug 33).
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

# Tkinter native DLLs — tcl/tk runtime, not auto-detected by cx_Freeze in conda envs.
# _tkinter.pyd is bundled automatically (not in EXCLUDES), but the native DLLs it
# loads (tcl86t.dll, tk86t.dll) are not — tk.Tk() fails at runtime without them.
for _dll in ('tcl86t.dll', 'tk86t.dll'):
    _p = _conda_bin / _dll
    if _p.exists():
        INCLUDE_FILES.append((str(_p), _dll))

# Tcl/Tk script libraries — tkinter reads these at runtime via TCL_LIBRARY/TK_LIBRARY.
# In conda envs they live at {prefix}/Library/lib/tcl8.6 and tk8.6.
# apf_manager_entry.py sets these env vars to the bundled paths when frozen.
_conda_lib = Path(sys.executable).parent / 'Library' / 'lib'
for _tcl_dir in ('tcl8.6', 'tk8.6'):
    _p = _conda_lib / _tcl_dir
    if _p.exists():
        # Placed in lib/ so tcl86t.dll's compiled-in search path ({dlldir}/lib/tcl8.6) finds them.
        # The existing inno_setup.iss lib/* recursive entry installs them without extra .iss entries.
        INCLUDE_FILES.append((str(_p), f'lib/{_tcl_dir}'))


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
# Pre-build: generate __version__.py with frozen build metadata
# ---------------------------------------------------------------------------

def _gen_version_file() -> None:
    """
    Write tools/apf_manager/__version__.py with the current git hash,
    manager version, and framework version (read from CMakeLists.txt).
    Called before setup() so cx_Freeze bundles the generated file.
    """
    import re
    import subprocess

    manager_ver = _MANAGER_VERSION

    # Framework version — regex from root CMakeLists.txt
    cmake_path = ROOT / "CMakeLists.txt"
    fw_ver = "?"
    try:
        m = re.search(
            r'project\s*\(\s*APFramework\s+VERSION\s+([\d.]+)',
            cmake_path.read_text(encoding="utf-8"),
        )
        if m:
            fw_ver = m.group(1)
    except Exception:
        pass

    # Short git hash
    build_id = "unknown"
    try:
        build_id = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            cwd=str(ROOT),
        ).strip()
    except Exception:
        pass

    version_file = HERE / "__version__.py"
    version_file.write_text(
        f'# Auto-generated by setup.py at freeze time — do not edit\n'
        f'__version__           = "{manager_ver}"\n'
        f'__build_id__          = "{build_id}"\n'
        f'__is_dev__            = False\n'
        f'__framework_version__ = "{fw_ver}"\n',
        encoding="utf-8",
    )
    print(f"Generated {version_file}")


if "build_exe" in sys.argv:
    _gen_version_file()


# ---------------------------------------------------------------------------
# Post-build hook: copy plugins/ and data/ into build output
# ---------------------------------------------------------------------------

def _post_build():
    build_dir = Path(build_options["build_exe"])
    if not build_dir.exists():
        return

    # Copy built-in plugins → build/APFManager/plugins/
    # Note: .github_token is now in data/ — the copy below handles it
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

    # blacklist.json is repo-only — never ship it to end users.
    # It is fetched live from GitHub per session; bundling it would
    # allow circumvention via a stale copy.
    _bl = build_dir / "data" / "blacklist.json"
    if _bl.exists():
        _bl.unlink()
        print(f"Removed data/blacklist.json from build output (repo-only)")

    # Generate versioned ISCC runner — avoids dirtying inno_setup.iss (committed file).
    # Usage: .\build\build_installer.ps1 [-IsccPath "D:\Programs\Inno Setup 7"]
    # -IsccPath accepts a directory or full exe path; falls back to PATH then common locations.
    ps1_path = HERE / "build" / "build_installer.ps1"
    ps1_path.parent.mkdir(parents=True, exist_ok=True)
    ps1_path.write_text(
        '# Auto-generated by setup.py — do not commit\n'
        '# Usage: .\\build_installer.ps1 [-IsccPath "D:\\Programs\\Inno Setup 7"]\n'
        '# -IsccPath can be a directory containing ISCC.exe or a full path to ISCC.exe.\n'
        '# When omitted, ISCC is discovered from PATH then common install locations.\n'
        '\n'
        'param(\n'
        '    [string]$IsccPath = ""\n'
        ')\n'
        '\n'
        '$iscc = $null\n'
        '\n'
        '# 0. Explicit override\n'
        'if ($IsccPath) {\n'
        '    if ($IsccPath -match \'\\.exe$\') {\n'
        '        $iscc = $IsccPath\n'
        '    } else {\n'
        '        $iscc = Join-Path $IsccPath "ISCC.exe"\n'
        '    }\n'
        '    if (-not (Test-Path $iscc)) {\n'
        '        Write-Error "ISCC.exe not found at: $iscc"\n'
        '        exit 1\n'
        '    }\n'
        '}\n'
        '\n'
        '# 1. Check PATH\n'
        'if (-not $iscc) {\n'
        '    $inPath = Get-Command iscc -ErrorAction SilentlyContinue\n'
        '    if ($inPath) { $iscc = $inPath.Source }\n'
        '}\n'
        '\n'
        '# 2. Common install locations\n'
        'if (-not $iscc) {\n'
        '    $candidates = @(\n'
        '        "$env:ProgramFiles\\Inno Setup 7\\ISCC.exe",\n'
        '        "$env:ProgramFiles\\Inno Setup 6\\ISCC.exe",\n'
        '        "${env:ProgramFiles(x86)}\\Inno Setup 7\\ISCC.exe",\n'
        '        "${env:ProgramFiles(x86)}\\Inno Setup 6\\ISCC.exe"\n'
        '    )\n'
        '    foreach ($c in $candidates) {\n'
        '        if (Test-Path $c) { $iscc = $c; break }\n'
        '    }\n'
        '}\n'
        '\n'
        'if (-not $iscc) {\n'
        '    Write-Error "ISCC.exe not found. Pass -IsccPath, install Inno Setup, or add it to your PATH."\n'
        '    exit 1\n'
        '}\n'
        '\n'
        f'& $iscc /DMyAppVersion="{_MANAGER_VERSION}" "$PSScriptRoot\\..\\inno_setup.iss"\n',
        encoding="utf-8",
    )
    print(f"Generated {ps1_path}  (run this instead of calling ISCC directly)")



# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

setup(
    name="APFManager",
    version=_MANAGER_VERSION,
    description="AP Framework Manager",
    options={"build_exe": build_options},
    executables=executables,
)

# Run post-build steps (only when actually building)
if "build_exe" in sys.argv:
    _post_build()
