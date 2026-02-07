#pragma once

// Include shared types from APShared library
#include "Types/ap_shared_enums.h"
#include "Types/ap_shared_ipc_types.h"
#include "Types/ap_shared_config_types.h"
#include "Types/ap_shared_manifest_types.h"

#include <string>

namespace ap {

// =============================================================================
// Client-Specific Types
// =============================================================================

// ClientIPCMessage is an alias for the shared IPCMessage
using ClientIPCMessage = IPCMessage;

// =============================================================================
// Log Level Priority Helper (for string-based level comparison)
// =============================================================================

inline int client_log_level_priority(const std::string& level) {
    if (level == "trace") return 0;
    if (level == "debug") return 1;
    if (level == "info") return 2;
    if (level == "warn" || level == "warning") return 3;
    if (level == "error") return 4;
    if (level == "fatal") return 5;
    return 2; // default to info
}

} // namespace ap