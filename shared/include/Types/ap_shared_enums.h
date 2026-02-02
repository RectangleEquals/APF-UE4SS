#pragma once

/**
 * @file ap_shared_enums.h
 * @brief Shared enumerations used by both APFrameworkCore and APClientLib.
 */

#include <string>

namespace ap {

// =============================================================================
// Log Level
// =============================================================================

/**
 * @brief Log severity levels.
 *
 * Levels are ordered from most verbose (Trace) to most severe (Fatal).
 * The configured log level determines the minimum severity that gets logged.
 */
enum class LogLevel {
    Trace = 0,  ///< Function entry/exit, variable values, loop iterations
    Debug = 1,  ///< IPC messages with full JSON, state decisions, AP server data
    Info = 2,   ///< Initialization, lifecycle transitions, connection state
    Warn = 3,   ///< Recoverable issues that shouldn't impact operation
    Error = 4,  ///< Issues likely to impact proper operation
    Fatal = 5   ///< Complete system failure
};

inline std::string log_level_to_string(LogLevel level) {
    switch (level) {
        case LogLevel::Trace: return "TRACE";
        case LogLevel::Debug: return "DEBUG";
        case LogLevel::Info:  return "INFO";
        case LogLevel::Warn:  return "WARN";
        case LogLevel::Error: return "ERROR";
        case LogLevel::Fatal: return "FATAL";
        default: return "UNKNOWN";
    }
}

inline LogLevel log_level_from_string(const std::string& str) {
    if (str == "trace" || str == "TRACE" || str == "Trace") return LogLevel::Trace;
    if (str == "debug" || str == "DEBUG" || str == "Debug") return LogLevel::Debug;
    if (str == "info" || str == "INFO" || str == "Info") return LogLevel::Info;
    if (str == "warn" || str == "WARN" || str == "Warn") return LogLevel::Warn;
    if (str == "error" || str == "ERROR" || str == "Error") return LogLevel::Error;
    if (str == "fatal" || str == "FATAL" || str == "Fatal") return LogLevel::Fatal;
    return LogLevel::Info;  // Default
}

// =============================================================================
// Item Type (for manifest items)
// =============================================================================

enum class ItemType {
    Progression,
    Useful,
    Filler,
    Trap
};

inline std::string item_type_to_string(ItemType type) {
    switch (type) {
        case ItemType::Progression: return "progression";
        case ItemType::Useful:      return "useful";
        case ItemType::Filler:      return "filler";
        case ItemType::Trap:        return "trap";
        default: return "unknown";
    }
}

inline ItemType item_type_from_string(const std::string& str) {
    if (str == "progression") return ItemType::Progression;
    if (str == "useful")      return ItemType::Useful;
    if (str == "filler")      return ItemType::Filler;
    if (str == "trap")        return ItemType::Trap;
    return ItemType::Filler;  // Default
}

// =============================================================================
// Argument Type (for action arguments in manifest)
// =============================================================================

enum class ArgType {
    String,
    Number,
    Boolean,
    Property
};

inline std::string arg_type_to_string(ArgType type) {
    switch (type) {
        case ArgType::String:   return "string";
        case ArgType::Number:   return "number";
        case ArgType::Boolean:  return "boolean";
        case ArgType::Property: return "property";
        default: return "unknown";
    }
}

inline ArgType arg_type_from_string(const std::string& str) {
    if (str == "string")   return ArgType::String;
    if (str == "number")   return ArgType::Number;
    if (str == "boolean")  return ArgType::Boolean;
    if (str == "property") return ArgType::Property;
    return ArgType::String;  // Default
}

} // namespace ap