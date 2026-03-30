# AP Framework — Developer Environment Setup

This guide covers setting up a local build environment for the **AP Framework C++ core** and the **APF Manager** tool. Read-only contributors (bug reports, PRs) can follow the Python/Manager section only; write-tier contributors building the framework DLLs need the full guide.

---

## Prerequisites

### C++ Toolchain

| Tool | Version | Notes |
|------|---------|-------|
| **Visual Studio 2022** | 17.x | Select the **"Desktop development with C++"** workload during install |
| **CMake** | 3.20+ | Included with VS, or install separately from cmake.org |
| **Ninja** | Any | Install via VS Installer → Individual components → "Ninja" |
| **vcpkg** | Latest | Bootstrap instructions below |

### Python

| Tool | Version | Notes |
|------|---------|-------|
| **Miniconda** or Anaconda | Any | Used to manage the APF Manager Python environment |
| **Python** | 3.12 | Installed via conda (see below) |

### VS Code Extensions (recommended)

- **C/C++** (Microsoft) — for IntelliSense fallback and debugging
- **CMake Tools** (Microsoft) — cmake configure/build UI integration
- **clangd** (LLVM) — primary code intelligence (disable MSVC IntelliSense once clangd is working)

---

## 1. vcpkg Bootstrap

vcpkg is used to provide OpenSSL, which is required by apclientpp for TLS WebSocket connections to Archipelago servers.

```powershell
# Clone vcpkg somewhere permanent (e.g. D:\Tools\vcpkg)
git clone https://github.com/microsoft/vcpkg D:\Tools\vcpkg
cd D:\Tools\vcpkg
.\bootstrap-vcpkg.bat

# Install the required package (x64 Windows)
.\vcpkg install openssl:x64-windows
```

If you install vcpkg somewhere other than `D:\Tools\vcpkg`, update `.vscode/settings.json`:

```json
{
    "cmake.configureSettings": {
        "CMAKE_TOOLCHAIN_FILE": "C:\\YourPath\\vcpkg\\scripts\\buildsystems\\vcpkg.cmake"
    }
}
```

---

## 2. Third-Party: SQLite3

SQLite3 is used for runtime queries in client mods. The amalgamation is not vendored in the repo due to file size — download it manually:

1. Go to [sqlite.org/download.html](https://www.sqlite.org/download.html)
2. Download **"sqlite-amalgamation-XXXXXXXX.zip"** (the C source amalgamation)
3. Extract `sqlite3.c` and `sqlite3.h` into:
   ```
   third_party/sqlite3/sqlite3.c
   third_party/sqlite3/sqlite3.h
   ```

CMake will detect these files automatically. The build will fail with a clear error if they are missing.

---

## 3. CMake Configure

Open the repository root in VS Code. CMake Tools will detect `CMakeLists.txt` automatically.

**Recommended settings** (`.vscode/settings.json`):

```json
{
    "cmake.buildDirectory": "${workspaceFolder}/build/${buildType}",
    "cmake.generator": "Ninja",
    "cmake.configureSettings": {
        "CMAKE_TOOLCHAIN_FILE": "D:\\Tools\\vcpkg\\scripts\\buildsystems\\vcpkg.cmake",
        "CMAKE_EXPORT_COMPILE_COMMANDS": "ON"
    },
    "cmake.copyCompileCommands": "${workspaceFolder}/compile_commands.json"
}
```

`CMAKE_EXPORT_COMPILE_COMMANDS` generates `compile_commands.json` at the repo root — required for clangd to resolve includes correctly.

**To configure:** Open the Command Palette (`Ctrl+Shift+P`) → **CMake: Configure**. Select the **Visual Studio 2022 Release - amd64** kit.

**FetchContent dependencies** are downloaded automatically at configure time (no manual steps):
- zlib, asio, nlohmann/json, websocketpp, wswrap, apclientpp, rapidyaml

This requires an internet connection on first configure.

---

## 4. Clangd Setup

Clangd provides superior code intelligence compared to MSVC IntelliSense for this project.

**`.vscode/settings.json` additions:**

```json
{
    "clangd.arguments": [
        "--compile-commands-dir=${workspaceFolder}",
        "--query-driver=C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Tools\\MSVC\\**\\bin\\Hostx64\\x64\\cl.exe",
        "--background-index",
        "--clang-tidy"
    ],
    "C_Cpp.intelliSenseEngine": "disabled"
}
```

Adjust the `--query-driver` path to match your VS 2022 installation. After configure (step 3), clangd will index the project using `compile_commands.json`.

---

## 5. Build

Press **Ctrl+Shift+B** (CMake: Build) or use the CMake Tools status bar button.

Output goes to `build/Release/` (or `build/Debug/` for debug builds).

The first build downloads FetchContent dependencies and may take several minutes. Subsequent builds are incremental.

**Version header:** CMake automatically runs `tools/scripts/gen_version_header.py` before compiling to generate `shared/include/apf_version_info.h` from the version in `CMakeLists.txt` and the current git hash. This file is gitignored — do not commit it.

---

## 6. Python / APF Manager

```powershell
# Create the conda environment (from repo root)
conda env create -f tools/apf_manager/environment.yml

# Activate it
conda activate apf_manager

# Run the manager in dev mode
cd tools
python -m apf_manager
```

**To run with Developer Tools enabled:**
```powershell
python -m apf_manager --devtools
```

---

## 7. `__version__.py` (required for a useful title bar)

Create `tools/apf_manager/__version__.py` locally — this file is gitignored and never committed:

```python
# Local dev copy — gitignored. Edit __version__ here to bump the Manager version before a release build.
# Do not edit other fields — setup.py overwrites them at freeze time.
__version__           = "0.2.7"
__build_id__          = "dev"
__is_dev__            = True
__framework_version__ = "?"
```

The app works without this file (the title bar shows `APF Manager v?.?.? (dev)`), but creating it gives a meaningful title. Keep `__version__` in sync with the version in `CMakeLists.txt` — or set it to whatever you like locally.

---

## 8. GitHub Token (Docs Viewer)

The Docs Viewer plugin uses the GitHub API to fetch documentation. Without a token, requests are rate-limited to 60/hour.

Create a Personal Access Token (classic) with `public_repo` scope at [github.com/settings/tokens](https://github.com/settings/tokens), then create the file:

```
tools/apf_manager/plugins/docs_viewer/.github_token
```

Paste the token as plain text. **Never commit this file** — it is gitignored.

Alternatively, use the **Login** button in the Developer Tools panel (`--devtools`) to authenticate via GitHub OAuth. The token will be stored at `~/.apf_manager/github_token.json` and shared across all plugins.

---

## 9. Versioning

Three independent version numbers exist in the project:

| Component | Source file | Field |
|-----------|------------|-------|
| **C++ Framework** | `CMakeLists.txt` | `project(APFramework VERSION x.y.z)` |
| **APF Manager** | `tools/apf_manager/__version__.py` | `__version__` |
| **Apworld** | `worlds/apf/archipelago.json` | `"world_version"` |

**`APF_BUILD_ID`** in the C++ startup log equals the short git hash of HEAD. A `-dirty` suffix means there are uncommitted local changes in the working tree. Clean checkouts at any real commit produce the same hash on any machine or in CI.

**To bump a version for release:**

1. Edit the version string in the appropriate source file
2. Commit to master
3. In APF Manager with `--devtools`, use the **Version Management** section to apply the namespaced tag (`framework/v1.0.1`, `manager/v1.0.1`, `apworld/v1.0.1`)

Tagging via the Developer Tools plugin keeps CI and release artifacts synchronized. **Do not push version tags manually.**

**Read-only contributors** (clone, build, open PRs): you do not manage versions. The repo owner and write-tier collaborators handle version bumps and tagging.

---

## Troubleshooting

**CMake can't find OpenSSL:**
Verify `CMAKE_TOOLCHAIN_FILE` points to `vcpkg/scripts/buildsystems/vcpkg.cmake` and that `vcpkg install openssl:x64-windows` completed without errors.

**SQLite3 not found:**
Check that `third_party/sqlite3/sqlite3.c` and `sqlite3.h` exist. Re-run CMake configure after adding them.

**clangd shows errors but the build succeeds:**
Run **CMake: Configure** once to regenerate `compile_commands.json`, then restart VS Code.

**`python -m apf_manager` fails with import errors:**
Make sure the `apf_manager` conda environment is activated (`conda activate apf_manager`).

**Title bar shows `APF Manager v?.?.? (dev)`:**
Create `tools/apf_manager/__version__.py` (see step 7 above).

**Docs Viewer shows rate limit warnings:**
Add a `.github_token` file or log in via Developer Tools (see step 8).
