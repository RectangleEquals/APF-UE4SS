#pragma once

/**
 * @file ap_config.h
 * @brief Configuration manager singleton for the AP Framework.
 *
 * Loads and provides access to framework_config.json settings.
 * Both APFrameworkCore and APClientLib use this singleton.
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation is in .cpp file
 * - Uses APPathUtil to find config path
 *
 * Configuration is loaded from JSON:
 * {
 *     "game_name": "Palworld",
 *     "version": "1.0.0",
 *     "ap_server": { "host": "localhost", "port": 38281, ... },
 *     "logging": { "level": "info", "file": "", "console": true },
 *     "timeouts": { ... },
 *     "threading": { ... }
 * }
 *
 * Note: id_base is NOT part of this config. It is the hardcoded constant
 * APF_GLOBAL_ID_BASE (defined in ap_types.h). Per-player ID uniqueness is
 * handled via per-slot offsets in slot_data, not by this config.
 */

#include "Types/ap_shared_config_types.h"

#include <filesystem>
#include <string>

namespace ap {

class APConfig {
public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey {
    private:
        friend class APConfig;
        explicit ConstructorKey() = default;
    };

    explicit APConfig(ConstructorKey);
    ~APConfig() = default;

    // Delete copy/move
    APConfig(const APConfig&) = delete;
    APConfig& operator=(const APConfig&) = delete;
    APConfig(APConfig&&) = delete;
    APConfig& operator=(APConfig&&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APConfig singleton.
     */
    static APConfig* get();

    // =========================================================================
    // Loading
    // =========================================================================

    /**
     * @brief Load configuration from a JSON file.
     * @param config_path Path to the configuration file.
     * @return true if loading succeeded, false otherwise.
     *
     * Missing values in the file will use defaults.
     * If the file doesn't exist, default configuration is used.
     */
    bool load(const std::filesystem::path& config_path);

    /**
     * @brief Load configuration from the default path.
     * @return true if loading succeeded, false otherwise.
     *
     * Uses APPathUtil::get()->get_config_path() to determine the path.
     */
    bool load_default();

    /**
     * @brief Save current configuration to a JSON file.
     * @param config_path Path to save the configuration file.
     * @return true if saving succeeded, false otherwise.
     */
    bool save(const std::filesystem::path& config_path) const;

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
    bool is_loaded() const { return loaded_; }

    // =========================================================================
    // Full Config Access
    // =========================================================================

    /**
     * @brief Get the full configuration structure.
     * @return Reference to the FrameworkConfig.
     */
    const FrameworkConfig& config() const { return config_; }

    // =========================================================================
    // Convenience Accessors
    // =========================================================================

    const std::string& get_game_name() const { return config_.game_name; }
    const std::string& get_version() const { return config_.version; }

    // Logging config (nested)
    LogLevel get_log_level() const { return config_.logging.level; }
    const std::string& get_log_file() const { return config_.logging.file; }
    bool get_log_to_console() const { return config_.logging.console; }
    bool get_log_append() const { return config_.logging.append; }

    // Server config
    const APServerConfig& get_ap_server() const { return config_.ap_server; }
    const std::string& get_ap_host() const { return config_.ap_server.host; }
    int get_ap_port() const { return config_.ap_server.port; }
    const std::string& get_slot_name() const { return config_.ap_server.slot_name; }

    // Timeouts
    const TimeoutConfig& get_timeouts() const { return config_.timeouts; }
    const RetryConfig& get_retry() const { return config_.timeouts.retry; }

    // Threading
    const ThreadingConfig& get_threading() const { return config_.threading; }

    // =========================================================================
    // Setters (for runtime configuration changes)
    // =========================================================================

    void set_game_name(const std::string& name) { config_.game_name = name; }
    void set_log_level(LogLevel level) { config_.logging.level = level; }

    void set_ap_server(const std::string& host, int port) {
        config_.ap_server.host = host;
        config_.ap_server.port = port;
    }

    void set_slot(const std::string& slot_name, const std::string& password = "") {
        config_.ap_server.slot_name = slot_name;
        config_.ap_server.password = password;
    }

private:
    FrameworkConfig config_;
    bool loaded_ = false;
    std::filesystem::path loaded_path_;
};

} // namespace ap