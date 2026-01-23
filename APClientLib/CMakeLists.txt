# APClientLib CMakeLists.txt
# Full implementation in Phase 03+
project(APClientLib)

set(SOURCES
    src/placeholder.cpp
)

set(HEADERS
    include/ap_clientlib_exports.h
)

add_library(APClientLib SHARED ${SOURCES} ${HEADERS})

target_include_directories(APClientLib
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/lua-5.4.7/src
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
        ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/sol2/include
)

# Dependencies linked in Phase 02+

target_compile_definitions(APClientLib PRIVATE
    AP_CLIENTLIB_EXPORTS
)

target_link_libraries(APClientLib PRIVATE lua_static)

set_target_properties(APClientLib PROPERTIES
    PREFIX ""
    OUTPUT_NAME "APClientLib"
)