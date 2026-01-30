# APClientLib CMakeLists.txt
project(APClientLib)

set(SOURCES
    src/main.cpp
    src/ap_ipc_client.cpp
    src/ap_path_util.cpp
    src/ap_action_executor.cpp
    src/ap_client_manager.cpp
)

set(HEADERS
    include/ap_clientlib_exports.h
    include/ap_client_types.h
    include/ap_client_manager.h
    include/ap_ipc_client.h
    include/ap_path_util.h
    include/ap_action_executor.h
)

add_library(APClientLib SHARED ${SOURCES} ${HEADERS})

target_include_directories(APClientLib
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/lua-5.4.7/src
    SYSTEM PUBLIC
        ${json_SOURCE_DIR}/single_include
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
        ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/sol2/include
)

target_compile_definitions(APClientLib PRIVATE
    AP_CLIENTLIB_EXPORTS
)

target_link_libraries(APClientLib PRIVATE lua_static)

target_compile_options(APClientLib
    PRIVATE
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4251>"    # needs to have dll-interface to be used by clients of class
        "$<$<CXX_COMPILER_ID:MSVC>:/wd5321>"    # nonstandard extension used
)

set_target_properties(APClientLib PROPERTIES
    PREFIX ""
    OUTPUT_NAME "APClientLib"
)
