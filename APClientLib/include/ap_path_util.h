#pragma once

#include "ap_clientlib_exports.h"

#include <string>
#include <filesystem>
#include <optional>

namespace ap::client {

/**
 * Static utility class for client-side path resolution.
 *
 * Uses a two-tier discovery strategy:
 * 1. Primary: Call UE4SS's IterateGameDirectories() via cached Lua state
 * 2. Fallback: Search upward from DLL location
 *
 * The framework mod folder is identified by content (framework_config.json + manifest.json),
 * not by name, allowing users to rename the mod folder.
 */
class APCLIENT_API APPathUtil {
public:
    APPathUtil() = delete;
    APPathUtil(const APPathUtil&) = delete;
    APPathUtil& operator=(const APPathUtil&) = delete;

    // =========================================================================
    // Path Queries
    // =========================================================================

    static bool is_absolute(const std::string& path);
    static bool is_absolute(const std::filesystem::path& path);

    static bool file_exists(const std::string& path);
    static bool file_exists(const std::filesystem::path& path);

    static bool directory_exists(const std::string& path);
    static bool directory_exists(const std::filesystem::path& path);

    // =========================================================================
    // DLL Location (Fallback)
    // =========================================================================

    static std::filesystem::path get_dll_path();
    static std::filesystem::path get_dll_directory();

    // =========================================================================
    // Directory Discovery
    // =========================================================================

    /** Find Win64/Binaries folder via IterateGameDirectories or DLL search */
    static std::optional<std::filesystem::path> find_binaries_folder();

    /** Find ue4ss folder (<binaries>/ue4ss/) */
    static std::optional<std::filesystem::path> find_ue4ss_folder();

    /** Find Mods folder (<ue4ss>/Mods/) */
    static std::optional<std::filesystem::path> find_mods_folder();

    /**
     * Find the framework mod folder by content, not name.
     * Searches for folder containing both framework_config.json AND manifest.json.
     */
    static std::optional<std::filesystem::path> find_framework_mod_folder();

    // =========================================================================
    // Well-Known File Paths
    // =========================================================================

    /** Get path to the shared log file */
    static std::filesystem::path get_log_path();

    // =========================================================================
    // File Operations
    // =========================================================================

    static bool ensure_directory_exists(const std::filesystem::path& path);
    static std::string read_file(const std::filesystem::path& path);
    static bool write_file(const std::filesystem::path& path, const std::string& content);

    // =========================================================================
    // Cache Management
    // =========================================================================

    /**
     * Force re-initialization of the path cache.
     * Call this after the Lua state becomes available (e.g., after first update())
     * to switch from DLL-based discovery to IterateGameDirectories.
     */
    static void reinitialize_cache();

private:
    static void initialize_cache();

    /** Primary: Try to initialize cache using IterateGameDirectories via cached Lua state */
    static bool try_init_from_lua();

    /** Fallback: Initialize cache by searching upward from DLL location */
    static bool try_init_from_dll();

    /** Search Mods folder for framework mod (by content) */
    static bool find_framework_mod_by_content();

    static std::filesystem::path cached_dll_path_;
    static std::filesystem::path cached_dll_directory_;
    static std::optional<std::filesystem::path> cached_binaries_folder_;
    static std::optional<std::filesystem::path> cached_ue4ss_folder_;
    static std::optional<std::filesystem::path> cached_mods_folder_;
    static std::optional<std::filesystem::path> cached_framework_mod_folder_;
    static bool cache_initialized_;
};

} // namespace ap::client
