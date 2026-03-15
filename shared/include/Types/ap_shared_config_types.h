#pragma once

/**
 * @file ap_shared_config_types.h
 * @brief Configuration structures shared by both libraries.
 *
 * These types match the framework_config.json format:
 * {
 *     "game_name": "Palworld",
 *     "version": "1.0.0",
 *     "ap_server": { "host": "localhost", "port": 38281, ... },
 *     "logging": { "level": "info", "file": "", "console": true },
 *     "timeouts": { ... },
 *     "threading": { ... }
 * }
 *
 * Note: id_base is NOT part of framework_config.json. It is a hardcoded framework
 * constant (APF_GLOBAL_ID_BASE = 6942067) defined in ap_types.h.
 */

#include "ap_shared_enums.h"

#include <string>

namespace ap {

// =============================================================================
// Logging Configuration (nested under "logging")
// =============================================================================

struct LoggingConfig {
    LogLevel level = LogLevel::Info;
    std::string file;           // Empty = file logging disabled
    bool console = true;
};

// =============================================================================
// Retry Configuration (nested under "timeouts.retry")
// =============================================================================

struct RetryConfig {
    int max_connection = 3;
    int max_ipc_message = 3;
    int initial_delay_ms = 1000;
    double backoff_multiplier = 2.0;
    int max_delay_ms = 10000;
};

// =============================================================================
// Timeout Configuration (includes retry as nested object)
// =============================================================================

struct TimeoutConfig {
    int priority_registration_ms = 30000;
    int registration_ms          = 60000;
    int connection_ms            = 30000;
    int ipc_message_ms           = 5000;
    int action_execution_ms      = 5000;
    RetryConfig retry;
};

// =============================================================================
// Threading Configuration
// =============================================================================

struct ThreadingConfig {
    int polling_interval_ms   = 16;
    int ipc_poll_interval_ms  = 10;   // Note: Obsolete - polling via manual update() calls
    int queue_max_size        = 1000;
    int shutdown_timeout_ms   = 5000;
};

// =============================================================================
// AP Server Configuration
// =============================================================================

struct APServerConfig {
    std::string host = "localhost";  // Note: "host" not "server"
    int port = 38281;
    std::string slot_name;
    std::string password;
    bool auto_reconnect = true;
};

// =============================================================================
// Framework Configuration (top-level structure)
// =============================================================================

struct FrameworkConfig {
    std::string game_name;
    std::string version;
    APServerConfig ap_server;
    LoggingConfig logging;
    TimeoutConfig timeouts;
    ThreadingConfig threading;
};

} // namespace ap