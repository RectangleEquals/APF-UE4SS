# APShared - Static library for code shared between APFrameworkCore and APClientLib
project(APShared)

set(SOURCES
    src/ap_path_util.cpp
    src/ap_config.cpp
    src/ap_logger.cpp
    src/ap_manifest.cpp
)

set(HEADERS
	# Exports
	include/ap_exports.h

    # Types
    include/Types/ap_shared_enums.h
    include/Types/ap_shared_ipc_types.h
    include/Types/ap_shared_config_types.h
    include/Types/ap_shared_manifest_types.h

    # Singletons and interfaces
    include/ap_manager_base.h
    include/ap_path_util.h
    include/ap_config.h
    include/ap_logger.h
    include/ap_manifest.h
)

add_library(APShared STATIC ${SOURCES} ${HEADERS})

target_include_directories(APShared
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/lua-5.4.7/src
    SYSTEM PUBLIC
        ${json_SOURCE_DIR}/single_include
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
        ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/sol2/include
)

target_link_libraries(APShared
    PRIVATE
        lua_static
)

target_compile_options(APShared
    PRIVATE
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4251>"    # needs to have dll-interface to be used by clients of class
        "$<$<CXX_COMPILER_ID:MSVC>:/wd5321>"    # nonstandard extension used
)

set_target_properties(APShared PROPERTIES
    POSITION_INDEPENDENT_CODE ON
)