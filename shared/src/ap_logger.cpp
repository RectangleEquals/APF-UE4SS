#include "ap_logger.h"
#include "ap_config.h"
#include "ap_manager_base.h"
#include "ap_path_util.h"

#include <chrono>
#include <ctime>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sol/sol.hpp>
#include <sstream>
#include <thread>

#ifdef _WIN32
#include <Windows.h>
#endif

namespace ap
{

// File-scope thread-local variable (can't be exported from DLL)
static thread_local std::string g_thread_name_ = "";

// =============================================================================
// Singleton Implementation
// =============================================================================

APLogger::APLogger(ConstructorKey)
{
    // Default constructor - init() must be called
}

APLogger::~APLogger()
{
    shutdown();
}

APLogger *APLogger::get()
{
    static std::unique_ptr<APLogger> instance = std::make_unique<APLogger>(ConstructorKey{});
    return instance.get();
}

// =============================================================================
// Initialization
// =============================================================================

void APLogger::init()
{
    if (initialized_)
    {
        return;
    }

    // Get log file path from config
    const std::string &log_file = APConfig::get()->get_log_file();

    // Open log file if path is non-empty
    if (!log_file.empty())
    {
        // Resolve path relative to framework folder if not absolute
        std::filesystem::path log_path;
        if (std::filesystem::path(log_file).is_absolute())
        {
            log_path = log_file;
        }
        else
        {
            auto framework_folder = APPathUtil::get()->find_framework_mod_folder();
            if (framework_folder)
            {
                log_path = *framework_folder / log_file;
            }
            else
            {
                log_path = log_file; // Use as-is
            }
        }

        // Ensure parent directory exists
        APPathUtil::get()->ensure_directory_exists(log_path.parent_path());

        log_file_.open(log_path, std::ios::out | std::ios::app);
        if (!log_file_.is_open())
        {
            // Failed to open log file - will still log to console if enabled
            std::cerr << "[APLogger] Failed to open log file: " << log_path << std::endl;
        }
    }

    initialized_ = true;

    // Set main thread name if not already set
    if (g_thread_name_.empty())
    {
        g_thread_name_ = "Main";
    }
}

void APLogger::shutdown()
{
    std::lock_guard<std::mutex> lock(file_mutex_);

    if (log_file_.is_open())
    {
        log_file_.flush();
        log_file_.close();
    }

    log_callback_ = nullptr;
    initialized_ = false;
}

// =============================================================================
// Logging Methods
// =============================================================================

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
    // Check log level from APConfig (not stored locally)
    if (level < APConfig::get()->get_log_level())
    {
        return;
    }

    write_log_entry(level, message);
}

void APLogger::log(LogLevel level, const std::string &component, const std::string &message)
{
    // Check log level from APConfig (not stored locally)
    if (level < APConfig::get()->get_log_level())
    {
        return;
    }

    std::string formatted = "[" + component + "] " + message;
    write_log_entry(level, formatted);
}

// =============================================================================
// Thread Name
// =============================================================================

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

// =============================================================================
// Callback
// =============================================================================

void APLogger::set_log_callback(LogCallback callback)
{
    std::lock_guard<std::mutex> lock(file_mutex_);
    log_callback_ = std::move(callback);
}

void APLogger::clear_log_callback()
{
    std::lock_guard<std::mutex> lock(file_mutex_);
    log_callback_ = nullptr;
}

// =============================================================================
// Private Methods
// =============================================================================

void APLogger::write_log_entry(LogLevel level, const std::string &message)
{
    std::string formatted = format_log_entry(level, message);

    // Copy callback while holding mutex
    LogCallback callback_copy;

    // Write to file (mutex protected)
    {
        std::lock_guard<std::mutex> lock(file_mutex_);

        if (log_file_.is_open())
        {
            log_file_ << formatted << std::endl;
            log_file_.flush();
        }

        callback_copy = log_callback_;
    }
    // Mutex released here - BEFORE any Lua calls

    // Write to console (check APConfig for console setting)
    if (APConfig::get()->get_log_to_console())
    {
        print_to_console(level, formatted);
    }

    // Call callback (outside mutex to prevent deadlock)
    if (callback_copy)
    {
        try
        {
            callback_copy(level, formatted);
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

void APLogger::print_to_console(LogLevel level, const std::string &formatted)
{
    // Ensure we have a newline-terminated version for Lua/Raw output
    std::string message = formatted;
    if (message.empty() || !message.ends_with('\n'))
    {
        message += '\n';
    }

    // Try to use Lua print if available (for UE4SS console integration)
    auto *manager = APManagerAccessor::get();
    if (manager && initialized_)
    {
        sol::state_view *lua = manager->get_cached_lua();
        if (lua)
        {
            try
            {
                sol::function print_func = (*lua)["print"];
                if (print_func.valid())
                {
                    print_func(message);
                    return;
                }
            }
            catch (...)
            {
                // Fall through to std::cout/cerr
            }
        }
    }

    // Fallback to standard streams
    if (level >= LogLevel::Error)
    {
        std::cerr << formatted << std::flush;
    }
    else
    {
        std::cout << formatted << std::flush;
    }
}

} // namespace ap