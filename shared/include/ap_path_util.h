#pragma once

/**
 * @file ap_path_util.h
 * @brief Path utility singleton for discovering UE4SS mod structure.
 *
 * Uses a two-tier discovery strategy:
 * 1. Primary: Use debug.getinfo via APManagerAccessor to get Lua source path
 * 2. Fallback: Search upward from DLL location
 *
 * The framework mod folder is identified by content (framework_config.json + manifest.json),
 * not by name, allowing users to rename the mod folder.
 *
 * Singleton Pattern: Pass-Key + Meyers
 * - get() implementation is in .cpp file
 * - Instance methods, not static - use APPathUtil::get()->method()
 * - Caches discovered paths (paths don't change at runtime)
 */

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace ap {

class APPathUtil {
public:
    // =========================================================================
    // Pass-Key + Meyers Singleton Pattern
    // =========================================================================

    struct ConstructorKey {
    private:
        friend class APPathUtil;
        explicit ConstructorKey() = default;
    };

    explicit APPathUtil(ConstructorKey);
    ~APPathUtil() = default;

    // Delete copy/move
    APPathUtil(const APPathUtil&) = delete;
    APPathUtil& operator=(const APPathUtil&) = delete;
    APPathUtil(APPathUtil&&) = delete;
    APPathUtil& operator=(APPathUtil&&) = delete;

    /**
     * @brief Get the singleton instance.
     * @return Pointer to the APPathUtil singleton.
     */
    static APPathUtil* get();

    // =========================================================================
    // Discovery Methods
    // =========================================================================

    /**
     * @brief Find the ue4ss folder.
     * @return Path to ue4ss folder, or nullopt if not found.
     */
    std::optional<std::filesystem::path> find_ue4ss_folder();

    /**
     * @brief Find the Mods folder.
     * @return Path to Mods folder, or nullopt if not found.
     */
    std::optional<std::filesystem::path> find_mods_folder();

    /**
     * @brief Find the framework mod folder by content.
     * @return Path to framework mod folder, or nullopt if not found.
     *
     * Searches for folder containing both framework_config.json AND manifest.json.
     */
    std::optional<std::filesystem::path> find_framework_mod_folder();

    /**
     * @brief Find the output folder.
     * @return Path to output folder, or nullopt if not found.
     *
     * Creates the output folder if it doesn't exist.
     */
    std::optional<std::filesystem::path> find_output_folder();

    /**
     * @brief Find the current mod folder using debug.getinfo.
     * @return Path to the mod folder containing the calling script.
     *
     * Scans up the Lua call stack to find the first non-C source file,
     * then navigates up from its path to find the mod folder.
     */
    std::optional<std::filesystem::path> find_current_mod_folder();

    // =========================================================================
    // Well-Known Paths
    // =========================================================================

    /**
     * @brief Get the path to the framework log file.
     * @return Path to ap_framework.log in the framework mod folder.
     */
    std::filesystem::path get_log_path();

    /**
     * @brief Get the path to the framework config file.
     * @return Path to framework_config.json in the framework mod folder.
     */
    std::filesystem::path get_config_path();

    /**
     * @brief Get the path to the session state file.
     * @return Path to session_state.json in the framework mod folder.
     */
    std::filesystem::path get_session_state_path();

    // =========================================================================
    // Path Queries
    // =========================================================================

    /**
     * @brief Check if a file exists.
     */
    bool file_exists(const std::filesystem::path& path) const;

    /**
     * @brief Check if a directory exists.
     */
    bool directory_exists(const std::filesystem::path& path) const;

    // =========================================================================
    // File Operations
    // =========================================================================

    /**
     * @brief Read entire file contents.
     * @param path Path to the file.
     * @return File contents, or empty string on failure.
     */
    std::string read_file(const std::filesystem::path& path) const;

    /**
     * @brief Write content to a file.
     * @param path Path to the file.
     * @param content Content to write.
     * @return true on success, false on failure.
     */
    bool write_file(const std::filesystem::path& path, const std::string& content) const;

    /**
     * @brief Ensure a directory exists, creating it if necessary.
     * @param path Path to the directory.
     * @return true if directory exists or was created, false on failure.
     */
    bool ensure_directory_exists(const std::filesystem::path& path) const;

    // =========================================================================
    // Cache Management
    // =========================================================================

    /**
     * @brief Clear all cached paths.
     */
    void clear_cache();

    /**
     * @brief Force re-initialization of the path cache.
     *
     * Call this after the Lua state becomes available to switch from
     * DLL-based discovery to debug.getinfo-based discovery.
     */
    void reinitialize_cache();

private:
    void initialize_cache();

    /**
     * @brief Try to initialize cache using debug.getinfo via APManagerAccessor.
     * @return true if successful, false otherwise.
     */
    bool try_init_from_lua();

    /**
     * @brief Fallback: Initialize cache by searching upward from DLL location.
     * @return true if successful, false otherwise.
     */
    bool try_init_from_dll();

    /**
     * @brief Search Mods folder for framework mod by content.
     * @return true if found, false otherwise.
     */
    bool find_framework_mod_by_content();

    /**
     * @brief Get the DLL's directory.
     * @return Path to the directory containing the DLL.
     */
    std::filesystem::path get_dll_directory() const;

    // Cached paths
    std::optional<std::filesystem::path> cached_ue4ss_folder_;
    std::optional<std::filesystem::path> cached_mods_folder_;
    std::optional<std::filesystem::path> cached_framework_folder_;
    std::filesystem::path cached_dll_directory_;
    bool cache_initialized_ = false;
};

} // namespace ap