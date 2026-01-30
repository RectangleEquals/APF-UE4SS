#include "ap_logger.h"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <thread>

#ifdef _WIN32
#include <Windows.h>
#endif

namespace ap
{

// File-scope thread-local variable (can't be exported from DLL)
static thread_local std::string g_thread_name_ = "";

APLogger &APLogger::instance()
{
    static APLogger instance;
    return instance;
}

APLogger::~APLogger()
{
    shutdown();
}

bool APLogger::init(LogLevel min_level, const std::string &log_file_path, bool console_output)
{
    std::lock_guard<std::mutex> lock(mutex_);

    if (initialized_)
    {
        return true;
    }

    min_level_ = min_level;
    console_output_ = console_output;

    if (!log_file_path.empty())
    {
        log_file_.open(log_file_path, std::ios::out | std::ios::app);
        if (!log_file_.is_open())
        {
            if (console_output_)
            {
                std::cerr << "[APLogger] Failed to open log file: " << log_file_path << std::endl;
            }
            return false;
        }
    }

    initialized_ = true;

    // Set main thread name
    if (g_thread_name_.empty())
    {
        g_thread_name_ = "Main";
    }

    return true;
}

void APLogger::shutdown()
{
    std::lock_guard<std::mutex> lock(mutex_);

    if (log_file_.is_open())
    {
        log_file_.flush();
        log_file_.close();
    }

    log_callback_ = nullptr;
    initialized_ = false;
}

void APLogger::trace(const std::string &message)
{
    log(LogLevel::Trace, message);
}

void APLogger::debug(const std::string &message)
{
    log(LogLevel::Debug, message);
}

void APLogger::info(const std::string &message)
{
    log(LogLevel::Info, message);
}

void APLogger::warn(const std::string &message)
{
    log(LogLevel::Warn, message);
}

void APLogger::error(const std::string &message)
{
    log(LogLevel::Error, message);
}

void APLogger::fatal(const std::string &message)
{
    log(LogLevel::Fatal, message);
}

void APLogger::log(LogLevel level, const std::string &message)
{
    if (level < min_level_)
    {
        return;
    }

    write_log_entry(level, message);
}

void APLogger::log(LogLevel level, const std::string &component, const std::string &message)
{
    if (level < min_level_)
    {
        return;
    }

    std::string formatted = "[" + component + "] " + message;
    write_log_entry(level, formatted);
}

void APLogger::set_min_level(LogLevel level)
{
    std::lock_guard<std::mutex> lock(mutex_);
    min_level_ = level;
}

LogLevel APLogger::get_min_level() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return min_level_;
}

void APLogger::set_console_output(bool enabled)
{
    std::lock_guard<std::mutex> lock(mutex_);
    console_output_ = enabled;
}

bool APLogger::get_console_output() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return console_output_;
}

void APLogger::set_log_callback(LogCallback callback)
{
    std::lock_guard<std::mutex> lock(mutex_);
    log_callback_ = std::move(callback);
}

void APLogger::clear_log_callback()
{
    std::lock_guard<std::mutex> lock(mutex_);
    log_callback_ = nullptr;
}

void APLogger::set_thread_name(const std::string &name)
{
    g_thread_name_ = name;

#ifdef _WIN32
    // Set thread name for debugger (Windows 10+)
    std::wstring wname(name.begin(), name.end());
    SetThreadDescription(GetCurrentThread(), wname.c_str());
#endif
}

std::string APLogger::get_thread_name()
{
    if (g_thread_name_.empty())
    {
        std::stringstream ss;
        ss << std::this_thread::get_id();
        return ss.str();
    }
    return g_thread_name_;
}

void APLogger::write_log_entry(LogLevel level, const std::string &message)
{
    std::lock_guard<std::mutex> lock(mutex_);

    std::string formatted = format_log_entry(level, message);

    // Write to file
    if (log_file_.is_open())
    {
        log_file_ << formatted << std::endl;
        log_file_.flush();
    }

    // Write to console
    if (console_output_)
    {
        // Use appropriate stream based on level
        if (level >= LogLevel::Error)
        {
            std::cerr << formatted << std::endl;
        }
        else
        {
            std::cout << formatted << std::endl;
        }
    }

    // Call callback if set
    if (log_callback_)
    {
        try
        {
            log_callback_(level, formatted);
        }
        catch (...)
        {
            // Ignore callback exceptions
        }
    }
}

std::string APLogger::get_timestamp() const
{
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(now.time_since_epoch()) % 1000;

    std::tm tm_buf;
#ifdef _WIN32
    localtime_s(&tm_buf, &time_t);
#else
    localtime_r(&time_t, &tm_buf);
#endif

    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%Y-%m-%d %H:%M:%S");
    oss << '.' << std::setfill('0') << std::setw(3) << ms.count();

    return oss.str();
}

std::string APLogger::format_log_entry(LogLevel level, const std::string &message) const
{
    std::ostringstream oss;
    oss << "[" << get_timestamp() << "]";
    oss << "[" << get_thread_name() << "]";
    oss << "[" << log_level_to_string(level) << "] ";
    oss << message;
    return oss.str();
}

} // namespace ap
