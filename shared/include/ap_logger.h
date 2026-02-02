#pragma once

/**
 * @file ap_logger.h
 * @brief Logging singleton for the AP Framework.
 *
 * Provides unified logging to file and console for both libraries.
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation is in .cpp file
 * - Gets all config from APConfig singleton (no redundant storage)
 *
 * Design:
 * - init() takes NO arguments - reads settings from APConfig
 * - Does NOT store log level or console flag - always reads from APConfig
 * - Logger is responsible for ALL logging (file + console)
 * - Uses APManagerAccessor for Lua print to console
 * - Mutex only protects file writes, released before Lua calls (deadlock prevention)
 *
 * Log Levels:
 * - TRACE: Function entry/exit, variable values, loop iterations
 * - DEBUG: IPC messages with full JSON, state decisions, AP server data
 * - INFO: Initialization, lifecycle transitions, connection state
 * - WARN: Recoverable issues that shouldn't impact operation
 * - ERROR: Issues likely to impact proper operation
 * - FATAL: Complete system failure
 */

#include "Types/ap_shared_enums.h"

#include <fstream>
#include <functional>
#include <mutex>
#include <string>

namespace ap {

class APLogger {
public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey {
    private:
        friend class APLogger;
        explicit ConstructorKey() = default;
    };

    explicit APLogger(ConstructorKey);
    ~APLogger();

    // Delete copy/move
    APLogger(const APLogger&) = delete;
    APLogger& operator=(const APLogger&) = delete;
    APLogger(APLogger&&) = delete;
    APLogger& operator=(APLogger&&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APLogger singleton.
     */
    static APLogger* get();

    // =========================================================================
    // Initialization
    // =========================================================================

    /**
     * @brief Initialize the logger.
     *
     * Reads settings from APConfig singleton:
     * - logging.level: Minimum log level to output
     * - logging.file: Log file path (empty = no file logging)
     * - logging.console: Whether to output to console
     *
     * Call this after APConfig::get()->load_default().
     */
    void init();

    /**
     * @brief Shutdown the logger.
     *
     * Flushes and closes the log file.
     */
    void shutdown();

    /**
     * @brief Check if the logger is initialized.
     */
    bool is_initialized() const { return initialized_; }

    // =========================================================================
    // Logging Methods
    // =========================================================================

    void trace(const std::string& message);
    void debug(const std::string& message);
    void info(const std::string& message);
    void warn(const std::string& message);
    void error(const std::string& message);
    void fatal(const std::string& message);

    /**
     * @brief Log a message with specified level.
     * @param level Log level.
     * @param message Message to log.
     */
    void log(LogLevel level, const std::string& message);

    /**
     * @brief Log a message with component tag.
     * @param level Log level.
     * @param component Component name (e.g., "IPC", "Manager").
     * @param message Message to log.
     */
    void log(LogLevel level, const std::string& component, const std::string& message);

    // =========================================================================
    // Thread Name (for log formatting)
    // =========================================================================

    /**
     * @brief Set the current thread's name for log output.
     * @param name Thread name.
     */
    static void set_thread_name(const std::string& name);

    /**
     * @brief Get the current thread's name.
     * @return Thread name, or thread ID if not set.
     */
    static std::string get_thread_name();

    // =========================================================================
    // Callback (for external log consumers)
    // =========================================================================

    using LogCallback = std::function<void(LogLevel level, const std::string& message)>;

    /**
     * @brief Set a callback for log messages.
     * @param callback Function to call for each log message.
     */
    void set_log_callback(LogCallback callback);

    /**
     * @brief Clear the log callback.
     */
    void clear_log_callback();

private:
    /**
     * @brief Format and write a log entry.
     */
    void write_log_entry(LogLevel level, const std::string& message);

    /**
     * @brief Get current timestamp string.
     */
    std::string get_timestamp() const;

    /**
     * @brief Format a complete log entry.
     */
    std::string format_log_entry(LogLevel level, const std::string& message) const;

    /**
     * @brief Print to console via Lua if available, or std::cout/cerr.
     *
     * Uses APManagerAccessor to get Lua state for lua["print"].
     * Falls back to std::cout/cerr if Lua is not available.
     */
    void print_to_console(LogLevel level, const std::string& formatted);

    std::ofstream log_file_;
    std::mutex file_mutex_;  // Only for file writes
    LogCallback log_callback_;
    bool initialized_ = false;
};

// =============================================================================
// Convenience Macros
// =============================================================================

#define AP_LOG_TRACE(msg) ap::APLogger::get()->trace(msg)
#define AP_LOG_DEBUG(msg) ap::APLogger::get()->debug(msg)
#define AP_LOG_INFO(msg) ap::APLogger::get()->info(msg)
#define AP_LOG_WARN(msg) ap::APLogger::get()->warn(msg)
#define AP_LOG_ERROR(msg) ap::APLogger::get()->error(msg)
#define AP_LOG_FATAL(msg) ap::APLogger::get()->fatal(msg)

#define AP_LOG_TRACE_F(component, msg) ap::APLogger::get()->log(ap::LogLevel::Trace, component, msg)
#define AP_LOG_DEBUG_F(component, msg) ap::APLogger::get()->log(ap::LogLevel::Debug, component, msg)
#define AP_LOG_INFO_F(component, msg) ap::APLogger::get()->log(ap::LogLevel::Info, component, msg)
#define AP_LOG_WARN_F(component, msg) ap::APLogger::get()->log(ap::LogLevel::Warn, component, msg)
#define AP_LOG_ERROR_F(component, msg) ap::APLogger::get()->log(ap::LogLevel::Error, component, msg)
#define AP_LOG_FATAL_F(component, msg) ap::APLogger::get()->log(ap::LogLevel::Fatal, component, msg)

} // namespace ap