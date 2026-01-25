#pragma once

#include "ap_types.h"
#include "ap_exports.h"

#include <string>
#include <fstream>
#include <mutex>
#include <functional>
#include <sstream>
#include <memory>

namespace ap {

class AP_API APLogger {
public:
    static APLogger& instance();

    APLogger(const APLogger&) = delete;
    APLogger& operator=(const APLogger&) = delete;

    bool init(LogLevel min_level, const std::string& log_file_path, bool console_output);
    void shutdown();

    void trace(const std::string& message);
    void debug(const std::string& message);
    void info(const std::string& message);
    void warn(const std::string& message);
    void error(const std::string& message);
    void fatal(const std::string& message);

    void log(LogLevel level, const std::string& message);
    void log(LogLevel level, const std::string& component, const std::string& message);

    void set_min_level(LogLevel level);
    LogLevel get_min_level() const;

    void set_console_output(bool enabled);
    bool get_console_output() const;

    using LogCallback = std::function<void(LogLevel level, const std::string& message)>;
    void set_log_callback(LogCallback callback);
    void clear_log_callback();

    static void set_thread_name(const std::string& name);
    static std::string get_thread_name();

private:
    APLogger() = default;
    ~APLogger();

    void write_log_entry(LogLevel level, const std::string& message);
    std::string get_timestamp() const;
    std::string format_log_entry(LogLevel level, const std::string& message) const;

    LogLevel min_level_ = LogLevel::Info;
    std::ofstream log_file_;
    bool console_output_ = true;
    bool initialized_ = false;
    LogCallback log_callback_;
    mutable std::mutex mutex_;
};

#define AP_LOG_TRACE(msg) ap::APLogger::instance().trace(msg)
#define AP_LOG_DEBUG(msg) ap::APLogger::instance().debug(msg)
#define AP_LOG_INFO(msg) ap::APLogger::instance().info(msg)
#define AP_LOG_WARN(msg) ap::APLogger::instance().warn(msg)
#define AP_LOG_ERROR(msg) ap::APLogger::instance().error(msg)
#define AP_LOG_FATAL(msg) ap::APLogger::instance().fatal(msg)

#define AP_LOG_TRACE_F(component, msg) ap::APLogger::instance().log(ap::LogLevel::Trace, component, msg)
#define AP_LOG_DEBUG_F(component, msg) ap::APLogger::instance().log(ap::LogLevel::Debug, component, msg)
#define AP_LOG_INFO_F(component, msg) ap::APLogger::instance().log(ap::LogLevel::Info, component, msg)
#define AP_LOG_WARN_F(component, msg) ap::APLogger::instance().log(ap::LogLevel::Warn, component, msg)
#define AP_LOG_ERROR_F(component, msg) ap::APLogger::instance().log(ap::LogLevel::Error, component, msg)
#define AP_LOG_FATAL_F(component, msg) ap::APLogger::instance().log(ap::LogLevel::Fatal, component, msg)

} // namespace ap
