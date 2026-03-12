# APFManifesto.spec
# Hand-crafted PyInstaller spec for APF Manifesto.
# DO NOT replace this with an auto-generated spec.
# Auto-generation omits kivy/kivymd datas and hiddenimports.

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Resolve venv site-packages (spec runs from app/ dir)
_venv = Path(SPECPATH).parent / ".venv" / "Lib" / "site-packages"

# ── Data files ──────────────────────────────────────────────────────────────
datas = []

# Kivy: data dir (shaders, fonts, atlas, default.kv, etc.)
datas += collect_data_files("kivy", includes=["**/*"])

# KivyMD: fonts, images, kv theme files
datas += collect_data_files("kivymd", includes=["**/*"])

# ── Hidden imports ───────────────────────────────────────────────────────────
hiddenimports = []

# Kivy backends / providers we actually need on Windows
hiddenimports += [
    "kivy.core.window.window_sdl2",
    "kivy.core.gl",
    "kivy.core.image.img_pil",
    "kivy.core.image.img_sdl2",
    "kivy.core.text.text_sdl2",
    "kivy.core.text.text_pil",
    "kivy.core.audio.audio_sdl2",
    "kivy.core.clipboard.clipboard_winctypes",
    "kivy.core.spelling",
    "kivy.input.providers.mouse",
    "kivy.input.providers.wm_touch",
    "kivy.input.providers.wm_pen",
    "kivy._event",
    "kivy._clock",
    "kivy.graphics.cgl_backend.cgl_glew",
]

# KivyMD: all uix submodules (avoids factory misses at runtime)
hiddenimports += collect_submodules("kivymd.uix")
hiddenimports += collect_submodules("kivymd.font_definitions")

# Our own app packages (relative imports need these)
hiddenimports += collect_submodules("app")

# PIL / Pillow
hiddenimports += collect_submodules("PIL")

# pywin32 -- required by kivy.uix.filechooser on Windows (win32api -> win32timezone)
hiddenimports += [
    "win32timezone",
    "win32api",
    "win32con",
    "win32gui",
    "pywintypes",
]

# ── Binaries ─────────────────────────────────────────────────────────────────
binaries = []

# SDL2 DLLs from kivy[base] wheel
_sdl2_bin = _venv / "kivy_deps" / "sdl2" / "share" / "sdl2" / "bin"
if not _sdl2_bin.exists():
    # kivy[base] bundles SDL2 directly under the venv share path
    _sdl2_bin = _venv.parent.parent / "share" / "sdl2" / "bin"
if _sdl2_bin.exists():
    for dll in _sdl2_bin.glob("*.dll"):
        binaries.append((str(dll), "."))

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    ["main.py"],
    pathex=[str(SPECPATH)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Trim unused heavy libs
        "numpy", "scipy", "pandas", "matplotlib",
        "tkinter", "unittest", "doctest",
        "pygame", "cv2", "ffpyplayer",
        "android", "jnius", "ios",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="APFManifesto",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
