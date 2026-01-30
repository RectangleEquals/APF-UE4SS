cmake_minimum_required(VERSION 3.20)
project(APFramework VERSION 1.0.0 LANGUAGES CXX)

# C++ Standard
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Export compile commands for clangd
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Fix third-party policy warnings
if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()

# Disable unnecessary build types
set (CMAKE_CONFIGURATION_TYPES "Debug;Release" CACHE STRING "Configurations" FORCE)

# --- Global Preprocessor Settings ---
add_compile_definitions(
    # asio
    ASIO_STANDALONE
    ASIO_NO_WIN32_LEAN_AND_MEAN
    
    # apclientpp
    AP_NO_SCHEMA

    # wswrap
    WSWRAP_NO_SSL

    # websocketpp
    WEBSOCKETPP_NO_TLS
    _WEBSOCKETPP_CPP11_STL_
    _WEBSOCKETPP_CPP11_STRICT_
    _WEBSOCKETPP_CPP11_CHRONO_

    # sol2
    SOL_ALL_SAFETIES_ON=1
)

if(WIN32)
    add_compile_definitions(
        _WIN32_WINNT=0x0601 # Windows 7+
        NOMINMAX            # Disable min/max macros
        WIN32_LEAN_AND_MEAN # Reduce Windows.h bloat
    )
endif()

# MSVC-specific settings
if(MSVC)
    add_compile_options(/W4 /permissive-)
    add_compile_options(/utf-8)     # UTF-8 source and execution charset

    # Disable specific warnings that are noisy with third-party code
    add_compile_options(/wd4100)    # unreferenced formal parameter
    add_compile_options(/wd4244)    # conversion, possible loss of data
    add_compile_options(/wd4267)    # conversion from 'size_t' to 'int', possible loss of data
    add_compile_options(/wd4840)    # non-portable use of class in variadic template
endif()

# Output directories
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)

# Options
option(AP_BUILD_FRAMEWORK "Build APFrameworkCore" ON)
option(AP_BUILD_CLIENTLIB "Build APClientLib" ON)
option(AP_BUILD_TESTS "Build tests" OFF)
option(AP_ENABLE_TSAN "Enable ThreadSanitizer (Debug builds)" OFF)

# Platform-specific settings
if(WIN32)
    add_definitions(-D_WIN32_WINNT=0x0601)  # Windows 7+
    add_definitions(-DNOMINMAX)              # Disable min/max macros
    add_definitions(-DWIN32_LEAN_AND_MEAN)   # Reduce Windows.h bloat
endif()

include(FetchContent)

# 1. ZLIB
set(ZLIB_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
FetchContent_Declare(
    zlib
    GIT_REPOSITORY https://github.com/madler/zlib.git
    GIT_TAG        v1.3.1
)

# 2. asio
# We set these variables BEFORE MakeAvailable to override its internal defaults
set(ASIO_STANDALONE ON CACHE BOOL "" FORCE)
set(ASIO_NO_WIN32_LEAN_AND_MEAN ON CACHE BOOL "" FORCE)
FetchContent_Declare(asio URL https://github.com/chriskohlhoff/asio/archive/f693a3eb7fe72a5f19b975289afc4f437d373d9c.zip)

# 3. nholmann/json
set(JSON_MultipleHeaders OFF CACHE BOOL "" FORCE)
FetchContent_Declare(json URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz)

# 4. websocketpp
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
FetchContent_Declare(websocketpp URL https://github.com/zaphoyd/websocketpp/archive/4dfe1be74e684acca19ac1cf96cce0df9eac2a2d.zip)

# 5. wswrap
# Desktop-only, without submodule:
set(WSWRAP_NO_SSL ON CACHE BOOL "" FORCE)
FetchContent_Declare(wswrap URL https://github.com/black-sliver/wswrap/archive/d0505e0ec53a26743f11051949a0dc66bcf44951.zip)
# Complete, with submodule:
# FetchContent_Declare(
#     wswrap
#     GIT_REPOSITORY https://github.com/black-sliver/wswrap.git
#     GIT_TAG d0505e0ec53a26743f11051949a0dc66bcf44951
# )

# 6. apclientpp
set(APCLIENTPP_BUILD_TESTING OFF CACHE BOOL "" FORCE)
FetchContent_Declare(
    apclientpp
    GIT_REPOSITORY https://github.com/black-sliver/apclientpp.git
    GIT_TAG        main
)

FetchContent_MakeAvailable(zlib asio json websocketpp wswrap apclientpp)

add_subdirectory(third_party/lua-5.4.7)

# Build targets
if(AP_BUILD_FRAMEWORK)
    add_subdirectory(APFrameworkCore)
endif()

if(AP_BUILD_CLIENTLIB)
    add_subdirectory(APClientLib)
endif()

if(AP_BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests)
endif()

# Install rules
include(GNUInstallDirs)
install(DIRECTORY Mods/ DESTINATION ${CMAKE_INSTALL_DATADIR}/Mods)