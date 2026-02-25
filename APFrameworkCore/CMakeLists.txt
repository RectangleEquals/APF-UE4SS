project(APFrameworkCore)

# Note: ap_logger.cpp, ap_path_util.cpp, ap_config.cpp are now in APShared
set(SOURCES
    src/ap_manager.cpp
    src/ap_ipc_server.cpp
    src/ap_client.cpp
    src/ap_polling_thread.cpp
    src/ap_mod_registry.cpp
    src/ap_capabilities.cpp
    src/ap_vocabulary.cpp
    src/ap_state_manager.cpp
    src/ap_message_router.cpp
    src/ap_tracker_engine.cpp
    src/main.cpp
)

# Note: ap_logger.h, ap_path_util.h, ap_config.h are now in APShared
set(HEADERS
    include/ap_manager.h
    include/ap_types.h
    include/ap_ipc_server.h
    include/ap_client.h
    include/ap_polling_thread.h
    include/ap_mod_registry.h
    include/ap_capabilities.h
    include/ap_vocabulary.h
    include/ap_state_manager.h
    include/ap_message_router.h
    include/ap_tracker_engine.h
    include/thread_safe_queue.h
    include/atomic_state.h
    include/stop_token.h
    include/retry_util.h
    include/message_queues.h
)

add_library(APFrameworkCore SHARED ${SOURCES} ${HEADERS})

target_include_directories(APFrameworkCore
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../shared/include
        ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/lua-5.4.7/src
    SYSTEM PUBLIC
        ${json_SOURCE_DIR}/single_include
        ${wswrap_SOURCE_DIR}/include
        ${asio_SOURCE_DIR}/asio/include
        ${websocketpp_SOURCE_DIR}
        ${zlib_SOURCE_DIR}
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
        ${CMAKE_CURRENT_SOURCE_DIR}/../third_party/sol2/include
)

target_compile_definitions(APFrameworkCore PRIVATE AP_EXPORTS)

target_link_libraries(APFrameworkCore
    PRIVATE
        APShared
        lua_static
        zlibstatic
        apclientpp
        OpenSSL::SSL
        OpenSSL::Crypto
)

# Windows needs crypt32 for OpenSSL certificate store access
if(WIN32)
    target_link_libraries(APFrameworkCore PRIVATE crypt32)
endif()

target_compile_options(lua_static
    PRIVATE
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4127>"    # conditional expression is constant
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4267>"    # conversion from 'size_t' to 'int', possible loss of data
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4310>"    # cast truncates constant value
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4324>"    # structure was padded to alignment specifier
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4701>"    # potentially uninitialized local variable used
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4702>"    # unreachable code
)

target_compile_options(zlib
    PRIVATE
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4127>"    # conditional expression is constant
)

target_compile_options(zlibstatic
    PRIVATE
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4127>"    # conditional expression is constant
)

target_compile_options(apclientpp
    INTERFACE
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4127>"    # conditional expression is constant
)

target_compile_options(APFrameworkCore
    PRIVATE
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4251>"    # needs to have dll-interface to be used by clients of class
        "$<$<CXX_COMPILER_ID:MSVC>:/wd4702>"    # unreachable code
        "$<$<CXX_COMPILER_ID:MSVC>:/wd5321>"    # nonstandard extension used
)

set_target_properties(APFrameworkCore PROPERTIES
    PREFIX ""
    OUTPUT_NAME "APFrameworkCore"
)