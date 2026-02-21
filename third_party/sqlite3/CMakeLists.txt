# SQLite3 amalgamation build
#
# Place sqlite3.c and sqlite3.h in this directory.
# Download from: https://www.sqlite.org/download.html (amalgamation package)

if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/sqlite3.c")
    message(FATAL_ERROR
        "SQLite amalgamation not found!\n"
        "Download from https://www.sqlite.org/download.html\n"
        "Place sqlite3.c and sqlite3.h in ${CMAKE_CURRENT_SOURCE_DIR}/")
endif()

add_library(sqlite3 STATIC sqlite3.c)

target_include_directories(sqlite3 PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

# Build as C, not C++
set_target_properties(sqlite3 PROPERTIES LINKER_LANGUAGE C)

# Recommended compile definitions for embedded use
target_compile_definitions(sqlite3 PRIVATE
    SQLITE_THREADSAFE=1
    SQLITE_OMIT_LOAD_EXTENSION
)

# Suppress warnings in third-party C code
if(MSVC)
    target_compile_options(sqlite3 PRIVATE /W0)
else()
    target_compile_options(sqlite3 PRIVATE -w)
endif()
