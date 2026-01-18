# Design09: Dependencies

> Full dependency tree, CMake configuration, and folder structures.

---

## APFrameworkCore Dependencies

```
APFrameworkCore
├── apclientpp (submodule: third_party/apclientpp)
│   ├── wswrap (submodule: third_party/wswrap)
│   ├── asio (FetchContent: third_party/asio)
│   ├── websocketpp (submodule: third_party/websocketpp)
│   └── valijson (submodule: third_party/valijson)
├── nlohmann::json (header-only: third_party/nlohmann/json.hpp)
├── sol2 (header-only: third_party/sol2/sol.hpp)
└── lua-5.4.7 (static lib: third_party/lua-5.4.7/)
```

### Dependency Details

| Dependency | Type | Purpose |
|------------|------|---------|
| **apclientpp** | Submodule | AP server communication (WebSocket client) |
| **wswrap** | Submodule | WebSocket wrapper for apclientpp |
| **asio** | FetchContent | Async I/O for networking |
| **websocketpp** | Submodule | WebSocket protocol implementation |
| **valijson** | Submodule | JSON schema validation |
| **nlohmann::json** | Header-only | JSON parsing/serialization |
| **sol2** | Header-only | C++/Lua bindings |
| **lua-5.4.7** | Static lib | Lua interpreter |

---

## APClientLib Dependencies

```
APClientLib
├── nlohmann::json (header-only: third_party/nlohmann/json.hpp)
├── sol2 (header-only: third_party/sol2/sol.hpp)
└── lua-5.4.7 (static lib: third_party/lua-5.4.7/)
```

APClientLib is intentionally lightweight — it doesn't need apclientpp since all AP communication goes through the framework.

---

## Folder Structures

### APFrameworkMod

```
APFrameworkMod/
├── Scripts/
│   ├── main.lua              # Entry point
│   ├── APFramework.lua       # Lua wrapper for APFrameworkCore
│   ├── APFrameworkCore.dll   # C++ framework core
│   ├── APClient.lua          # Lua wrapper for APClientLib (optional)
│   ├── APClientLib.dll       # C++ client library
│   ├── registry_helper.lua   # UE4SS hook utilities
│   ├── lunajson.lua          # JSON library for Lua
│   └── lunajson/             # lunajson module folder
│       ├── decoder.lua
│       ├── encoder.lua
│       └── sax.lua
├── framework_config.json     # Framework configuration
└── output/                   # Generated files
    └── AP_Capabilities_*.json
```

### AP Client Mods

```
<mod_name>/
├── Scripts/
│   ├── main.lua              # Mod entry point
│   ├── APClient.lua          # Lua wrapper for APClientLib
│   ├── APClientLib.dll       # C++ client library
│   ├── lunajson.lua          # JSON library for Lua
│   └── lunajson/             # lunajson module folder
│       ├── decoder.lua
│       ├── encoder.lua
│       └── sax.lua
└── manifest.json             # Mod manifest with capabilities
```

### Source Project Structure

```
ipc_2/
├── APFrameworkCore/
│   ├── include/
│   │   ├── APManager.h
│   │   ├── APClient.h
│   │   ├── APIPCServer.h
│   │   ├── APCapabilities.h
│   │   ├── APModRegistry.h
│   │   ├── APMessageRouter.h
│   │   ├── APStateManager.h
│   │   ├── APPollingThread.h
│   │   ├── APConfig.h
│   │   ├── APPathUtil.h
│   │   ├── APLogger.h
│   │   └── ap_types.h
│   ├── src/
│   │   ├── APClient.cpp
│   │   ├── APIPCServer.cpp
│   │   ├── APCapabilities.cpp
│   │   ├── APModRegistry.cpp
│   │   ├── APMessageRouter.cpp
│   │   ├── APStateManager.cpp
│   │   ├── APPollingThread.cpp
│   │   ├── APConfig.cpp
│   │   ├── APPathUtil.cpp
│   │   └── APLogger.cpp
├── clientlib/
│   ├── include/
│   │   ├── APIPCClient.h
│   │   ├── APActionExecutor.h
│   │   ├── APPathUtil.h
│   │   └── APLogger.h
│   ├── src/
│   │   ├── APIPCClient.cpp
│   │   ├── APActionExecutor.cpp
│   │   ├── APPathUtil.cpp      # Shared with framework
│   │   └── APLogger.cpp        # Shared with framework
├── third_party/
│   ├── apclientpp/             # Submodule
│   │   ├── wswrap/             # Submodule
│   │   ├── websocketpp/        # Submodule
│   │   └── valijson/           # Submodule
│   ├── asio/                   # FetchContent
│   ├── nlohmann/
│   │   └── json.hpp
│   ├── sol2/
│   │   └── sol.hpp
│   ├── lua-5.4.7/
│   │   ├── src/
│   │   └── CMakeLists.txt
│   └── lua/
│       ├── APFramework.lua
│       ├── APClient.lua
│       └── registry_helper.lua
│       ├── lunajson.lua
│       └── lunajson/
├── docs/
│   ├── Architecture/
│   │   ├── ARCHITECTURE.md
│   │   ├── Design01_SystemComponents.md
│   │   └── ...
│   └── .claude/
│       ├── Implementation/
│       │   ├── Implementation.md
│       │   ├── Phase01_ProjectSetup.md
│       │   └── ...
│       └── AP_DOCS/
├── CMakeLists.txt
└── README.md
```

---

## CMake Configuration

### Root CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.20)
project(APFramework VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Options
option(BUILD_FRAMEWORK "Build APFrameworkCore" ON)
option(BUILD_CLIENTLIB "Build APClientLib" ON)
option(BUILD_TESTS "Build tests" OFF)

# Dependencies
include(FetchContent)

# Asio (standalone, header-only)
FetchContent_Declare(
    asio_fetch
    GIT_REPOSITORY https://github.com/chriskohlhoff/asio.git
    GIT_TAG asio-1-12-2
    SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/third_party/asio
)
FetchContent_MakeAvailable(asio_fetch)

# Lua
add_subdirectory(third_party/lua-5.4.7)

# Header-only libraries
add_library(nlohmann_json INTERFACE)
target_include_directories(nlohmann_json INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party)

add_library(sol2 INTERFACE)
target_include_directories(sol2 INTERFACE
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party)

# Submodules
add_subdirectory(third_party/apclientpp)

# Build targets
if(BUILD_FRAMEWORK)
    add_subdirectory(src/framework)
endif()

if(BUILD_CLIENTLIB)
    add_subdirectory(src/clientlib)
endif()

if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()
```

### Framework CMakeLists.txt

```cmake
# src/framework/CMakeLists.txt

add_library(APFrameworkCore SHARED
    APManager.cpp
    APClient.cpp
    APIPCServer.cpp
    APCapabilities.cpp
    APModRegistry.cpp
    APMessageRouter.cpp
    APStateManager.cpp
    APPollingThread.cpp
    APConfig.cpp
    APPathUtil.cpp
    APLogger.cpp
)

target_include_directories(APFrameworkCore
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}
    PRIVATE ${CMAKE_SOURCE_DIR}/third_party
    PRIVATE ${CMAKE_SOURCE_DIR}/third_party/apclientpp/include
    PRIVATE ${CMAKE_SOURCE_DIR}/third_party/asio/asio/include
)

target_link_libraries(APFrameworkCore
    PRIVATE apclientpp
    PRIVATE nlohmann_json
    PRIVATE sol2
    PRIVATE lua_static
    PRIVATE ws2_32  # Windows sockets
)

target_compile_definitions(APFrameworkCore
    PRIVATE ASIO_STANDALONE
    PRIVATE _WEBSOCKETPP_CPP11_THREAD_
    PRIVATE AP_FRAMEWORK_EXPORTS
)

# Export function for Lua loading
set_target_properties(APFrameworkCore PROPERTIES
    PREFIX ""
    OUTPUT_NAME "APFrameworkCore"
)

# Install
install(TARGETS APFrameworkCore
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
)
```

### ClientLib CMakeLists.txt

```cmake
# src/clientlib/CMakeLists.txt

add_library(APClientLib SHARED
    APIPCClient.cpp
    APActionExecutor.cpp
    APPathUtil.cpp
    APLogger.cpp
)

target_include_directories(APClientLib
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}
    PRIVATE ${CMAKE_SOURCE_DIR}/third_party
)

target_link_libraries(APClientLib
    PRIVATE nlohmann_json
    PRIVATE sol2
    PRIVATE lua_static
)

target_compile_definitions(APClientLib
    PRIVATE AP_CLIENTLIB_EXPORTS
)

# Export function for Lua loading
set_target_properties(APClientLib PROPERTIES
    PREFIX ""
    OUTPUT_NAME "APClientLib"
)

# Install
install(TARGETS APClientLib
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
)
```

### Lua CMakeLists.txt

```cmake
# third_party/lua-5.4.7/CMakeLists.txt

add_library(lua_static STATIC
    src/lapi.c
    src/lauxlib.c
    src/lbaselib.c
    src/lcode.c
    src/lcorolib.c
    src/lctype.c
    src/ldblib.c
    src/ldebug.c
    src/ldo.c
    src/ldump.c
    src/lfunc.c
    src/lgc.c
    src/linit.c
    src/liolib.c
    src/llex.c
    src/lmathlib.c
    src/lmem.c
    src/loadlib.c
    src/lobject.c
    src/lopcodes.c
    src/loslib.c
    src/lparser.c
    src/lstate.c
    src/lstring.c
    src/lstrlib.c
    src/ltable.c
    src/ltablib.c
    src/ltm.c
    src/lundump.c
    src/lutf8lib.c
    src/lvm.c
    src/lzio.c
)

target_include_directories(lua_static PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)

if(WIN32)
    target_compile_definitions(lua_static PRIVATE LUA_BUILD_AS_DLL)
endif()
```

---

## DLL Export Configuration

### APFrameworkCore Export

```cpp
// ap_exports.h
#pragma once

#ifdef _WIN32
    #ifdef AP_FRAMEWORK_EXPORTS
        #define AP_API __declspec(dllexport)
    #else
        #define AP_API __declspec(dllimport)
    #endif
#else
    #define AP_API
#endif

// Lua entry point
extern "C" {
    AP_API int luaopen_APFrameworkCore(lua_State* L);
}
```

### APClientLib Export

```cpp
// ap_clientlib_exports.h
#pragma once

#ifdef _WIN32
    #ifdef AP_CLIENTLIB_EXPORTS
        #define APCLIENT_API __declspec(dllexport)
    #else
        #define APCLIENT_API __declspec(dllimport)
    #endif
#else
    #define APCLIENT_API
#endif

// Lua entry point
extern "C" {
    APCLIENT_API int luaopen_APClientLib(lua_State* L);
}
```

---

## Build Instructions

### Prerequisites

- CMake 3.20+
- Visual Studio 2019+ (Windows)
- Git (for submodules)

### Clone with Submodules

```bash
git clone --recursive https://github.com/user/ap-framework.git
cd ap-framework
```

### Build

```bash
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

### Output

After building:

```
build/
├── Release/
│   ├── APFrameworkCore.dll
│   └── APClientLib.dll
```

### Deploy

Copy to UE4SS mod folders:

```bash
# Framework mod
cp Release/APFrameworkCore.dll <game>/Binaries/Win64/ue4ss/Mods/APFrameworkMod/Scripts/
cp Release/APClientLib.dll <game>/Binaries/Win64/ue4ss/Mods/APFrameworkMod/Scripts/

# Client mods
cp Release/APClientLib.dll <game>/Binaries/Win64/ue4ss/Mods/<mod_name>/Scripts/
```

---

## UE4SS Mod Types Note

| Type | Location | Description |
|------|----------|-------------|
| UE4SS C++ Mod | `ue4ss/Mods/<mod>/dlls/main.dll` | Built against UE4SS toolchain. **Avoided** - version compatibility issues. |
| UE4SS Lua Mod | `ue4ss/Mods/<mod>/Scripts/main.lua` | Can load C++ libraries via `require`. **Preferred approach.** |
| C++ Library | `*.dll` in Scripts folder | Normal DLL with Lua bindings via sol2. **Our approach.** |

The framework uses the C++ Library approach — DLLs with sol2 bindings loaded by Lua mods via `require()`.