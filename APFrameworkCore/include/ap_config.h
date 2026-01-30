#pragma once

#include "ap_exports.h"
#include "ap_types.h"

#include <filesystem>
#include <optional>
#include <string>

namespace ap
{

/**
 * @brief Configuration manager for the AP Framework.
 *
 * Singleton class that loads and provides access to framework configuration.
 * Configuration is loaded from a JSON file, with defaults for any missing values.
 */
class AP_API APConfig
{
  public:
    /**
     * @brief Get the singleton instance.
     * @return Reference to the APConfig singleton.
     */
    static APConfig &instance();

    // Delete copy/move operations
    APConfig(const APConfig &) = delete;
    APConfig &operator=(const APConfig &) = delete;
    APConfig(APConfig &&) = delete;
    APConfig &operator=(APConfig &&) = delete;

    /**
     * @brief Load configuration from a JSON file.
     * @param config_path Path to the configuration file.
     * @return true if loading succeeded, false otherwise.
     *
     * Missing values in the file will use defaults.
     * If the file doesn't exist, default configuration is used.
     */
    bool load(const std::filesystem::path &config_path);

    /**
     * @brief Load configuration from the default path.
     * @return true if loading succeeded, false otherwise.
     *
     * Uses APPathUtil::get_config_path() to determine the path.
     */
    bool load_default();

    /**
     * @brief Save current configuration to a JSON file.
     * @param config_path Path to save the configuration file.
     * @return true if saving succeeded, false otherwise.
     */
    bool save(const std::filesystem::path &config_path) const;

    /**
     * @brief Save current configuration to the default path.
     * @return true if saving succeeded, false otherwise.
     */
    bool save_default() const;

    /**
     * @brief Reset configuration to defaults.
     */
    void reset_to_defaults();

    /**
     * @brief Check if configuration has been loaded.
     * @return true if configuration is loaded, false otherwise.
     */
    bool is_loaded() const
    {
        return loaded_;
    }

    // ==========================================================================
    // Configuration Accessors
    // ==========================================================================

    const FrameworkConfig &get() const
    {
        return config_;
    }
    FrameworkConfig &get()
    {
        return config_;
    }

    // Convenience accessors
    const std::string &get_game_name() const
    {
        return config_.game_name;
    }
    int64_t get_id_base() const
    {
        return config_.id_base;
    }
    // const std::string &get_version() const
    // {
    //     return config_.version;
    // }
    LogLevel get_log_level() const
    {
        return config_.log_level;
    }
    const std::string &get_log_file() const
    {
        return config_.log_file;
    }
    bool get_log_to_console() const
    {
        return config_.log_to_console;
    }

    const TimeoutConfig &get_timeouts() const
    {
        return config_.timeouts;
    }
    const RetryConfig &get_retry() const
    {
        return config_.retry;
    }
    const ThreadingConfig &get_threading() const
    {
        return config_.threading;
    }
    const APServerConfig &get_ap_server() const
    {
        return config_.ap_server;
    }

    // ==========================================================================
    // Configuration Setters
    // ==========================================================================

    void set_game_name(const std::string &name)
    {
        config_.game_name = name;
    }
    void set_log_level(LogLevel level)
    {
        config_.log_level = level;
    }
    void set_ap_server(const std::string &server, int port)
    {
        config_.ap_server.server = server;
        config_.ap_server.port = port;
    }
    void set_slot(const std::string &slot_name, const std::string &password = "")
    {
        config_.ap_server.slot_name = slot_name;
        config_.ap_server.password = password;
    }

  private:
    APConfig() = default;
    ~APConfig() = default;

    FrameworkConfig config_;
    bool loaded_ = false;
    std::filesystem::path loaded_path_;
};

} // namespace ap
