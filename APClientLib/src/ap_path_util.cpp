#include "ap_path_util.h"
#include "ap_client_manager.h"

#include <sol/sol.hpp>

#include <fstream>
#include <sstream>
#include <memory>

#ifdef _WIN32
#include <Windows.h>

extern "C" IMAGE_DOS_HEADER __ImageBase;
#endif

namespace ap::client {

// =============================================================================
// Static Member Initialization
// =============================================================================

std::filesystem::path APPathUtil::cached_dll_path_;
std::filesystem::path APPathUtil::cached_dll_directory_;
std::optional<std::filesystem::path> APPathUtil::cached_binaries_folder_;
std::optional<std::filesystem::path> APPathUtil::cached_ue4ss_folder_;
std::optional<std::filesystem::path> APPathUtil::cached_mods_folder_;
std::optional<std::filesystem::path> APPathUtil::cached_framework_mod_folder_;
bool APPathUtil::cache_initialized_ = false;

// =============================================================================
// Cache Management
// =============================================================================

void APPathUtil::initialize_cache() {
    if (cache_initialized_) {
        return;
    }

    // Always get DLL path first (needed for fallback)
#ifdef _WIN32
    wchar_t dll_path[MAX_PATH];
    HMODULE hModule = reinterpret_cast<HMODULE>(&__ImageBase);
    DWORD len = GetModuleFileNameW(hModule, dll_path, MAX_PATH);

    if (len > 0 && len < MAX_PATH) {
        cached_dll_path_ = std::filesystem::path(dll_path);
        cached_dll_directory_ = cached_dll_path_.parent_path();
    }
#endif

    // Strategy 1: Try IterateGameDirectories via cached Lua state
    if (try_init_from_lua()) {
        cache_initialized_ = true;
        return;
    }

    // Strategy 2: Fallback to DLL-relative search
    if (try_init_from_dll()) {
        cache_initialized_ = true;
        return;
    }

    // Both failed - cache is still considered initialized (with empty values)
    cache_initialized_ = true;
}

void APPathUtil::reinitialize_cache() {
    // Reset all cached values
    cache_initialized_ = false;
    cached_binaries_folder_.reset();
    cached_ue4ss_folder_.reset();
    cached_mods_folder_.reset();
    cached_framework_mod_folder_.reset();

    // Re-run initialization (will try Lua first if available)
    initialize_cache();
}

bool APPathUtil::try_init_from_lua() {
    // Access the library's cached Lua state from APClientManager
    sol::state_view* lua = APClientManager::instance().get_lua_state();
    if (!lua) {
        return false;
    }

    try {
        // Check if IterateGameDirectories exists
        sol::object func = (*lua)["IterateGameDirectories"];
        if (!func.is<sol::function>()) {
            return false;
        }

        // Call IterateGameDirectories()
        sol::protected_function iterate = func.as<sol::function>();
        sol::protected_function_result result = iterate();
        if (!result.valid() || !result.get<sol::object>().is<sol::table>()) {
            return false;
        }

        sol::table dirs = result.get<sol::table>();

        // Navigate: dirs.Game.Binaries.Win64.__absolute_path
        sol::optional<sol::table> game = dirs["Game"];
        if (!game) {
            return false;
        }

        sol::optional<sol::table> binaries = (*game)["Binaries"];
        if (!binaries) {
            return false;
        }

        sol::optional<sol::table> win64 = (*binaries)["Win64"];
        if (!win64) {
            return false;
        }

        sol::optional<std::string> binaries_path = (*win64)["__absolute_path"];
        if (!binaries_path || binaries_path->empty()) {
            return false;
        }

        std::filesystem::path binaries_dir(*binaries_path);

        // Verify the path exists
        if (!directory_exists(binaries_dir)) {
            return false;
        }

        cached_binaries_folder_ = binaries_dir;

        // Look for ue4ss folder in Binaries
        std::filesystem::path ue4ss_path = binaries_dir / "ue4ss";
        if (directory_exists(ue4ss_path)) {
            cached_ue4ss_folder_ = ue4ss_path;

            std::filesystem::path mods_path = ue4ss_path / "Mods";
            if (directory_exists(mods_path)) {
                cached_mods_folder_ = mods_path;
            }
        }

        // Find framework mod by content
        find_framework_mod_by_content();

        return true;

    } catch (...) {
        // Any exception means Lua discovery failed
        return false;
    }
}

bool APPathUtil::try_init_from_dll() {
    // DLL path should already be set in initialize_cache()
    if (cached_dll_directory_.empty()) {
        return false;
    }

    // Search upward from DLL location for "ue4ss" folder
    // Expected structure: <game>/Binaries/Win64/ue4ss/Mods/<ModFolder>/Scripts/APClientLib.dll
    // Or: <game>/Binaries/Win64/ue4ss/Mods/<ModFolder>/APClientLib.dll

    std::filesystem::path search_path = cached_dll_directory_;
    for (int i = 0; i < 6 && !search_path.empty(); ++i) {
        if (search_path.filename() == "ue4ss") {
            cached_ue4ss_folder_ = search_path;
            cached_binaries_folder_ = search_path.parent_path();

            std::filesystem::path mods_path = search_path / "Mods";
            if (directory_exists(mods_path)) {
                cached_mods_folder_ = mods_path;
            }
            break;
        }
        search_path = search_path.parent_path();
    }

    // Find framework mod by content
    find_framework_mod_by_content();

    // Consider DLL init successful if we found the ue4ss folder
    return cached_ue4ss_folder_.has_value();
}

bool APPathUtil::find_framework_mod_by_content() {
    if (!cached_mods_folder_ || !directory_exists(*cached_mods_folder_)) {
        return false;
    }

    std::error_code ec;
    for (const auto& entry : std::filesystem::directory_iterator(*cached_mods_folder_, ec)) {
        if (ec || !entry.is_directory()) {
            continue;
        }

        // Framework mod must contain both framework_config.json AND manifest.json
        auto config_path = entry.path() / "framework_config.json";
        auto manifest_path = entry.path() / "manifest.json";

        if (file_exists(config_path) && file_exists(manifest_path)) {
            cached_framework_mod_folder_ = entry.path();
            return true;
        }
    }

    return false;
}

// =============================================================================
// Path Queries
// =============================================================================

bool APPathUtil::is_absolute(const std::string& path) {
    return std::filesystem::path(path).is_absolute();
}

bool APPathUtil::is_absolute(const std::filesystem::path& path) {
    return path.is_absolute();
}

bool APPathUtil::file_exists(const std::string& path) {
    return file_exists(std::filesystem::path(path));
}

bool APPathUtil::file_exists(const std::filesystem::path& path) {
    std::error_code ec;
    return std::filesystem::is_regular_file(path, ec) && !ec;
}

bool APPathUtil::directory_exists(const std::string& path) {
    return directory_exists(std::filesystem::path(path));
}

bool APPathUtil::directory_exists(const std::filesystem::path& path) {
    std::error_code ec;
    return std::filesystem::is_directory(path, ec) && !ec;
}

// =============================================================================
// DLL Location
// =============================================================================

std::filesystem::path APPathUtil::get_dll_path() {
    initialize_cache();
    return cached_dll_path_;
}

std::filesystem::path APPathUtil::get_dll_directory() {
    initialize_cache();
    return cached_dll_directory_;
}

// =============================================================================
// Directory Discovery
// =============================================================================

std::optional<std::filesystem::path> APPathUtil::find_binaries_folder() {
    initialize_cache();
    return cached_binaries_folder_;
}

std::optional<std::filesystem::path> APPathUtil::find_ue4ss_folder() {
    initialize_cache();
    return cached_ue4ss_folder_;
}

std::optional<std::filesystem::path> APPathUtil::find_mods_folder() {
    initialize_cache();
    return cached_mods_folder_;
}

std::optional<std::filesystem::path> APPathUtil::find_framework_mod_folder() {
    initialize_cache();
    return cached_framework_mod_folder_;
}

// =============================================================================
// Well-Known File Paths
// =============================================================================

std::filesystem::path APPathUtil::get_log_path() {
    auto framework_folder = find_framework_mod_folder();
    if (framework_folder) {
        return *framework_folder / "ap_framework.log";
    }

    // Fallback to DLL directory
    initialize_cache();
    return cached_dll_directory_ / "ap_framework.log";
}

// =============================================================================
// File Operations
// =============================================================================

bool APPathUtil::ensure_directory_exists(const std::filesystem::path& path) {
    if (directory_exists(path)) {
        return true;
    }

    std::error_code ec;
    return std::filesystem::create_directories(path, ec) && !ec;
}

std::string APPathUtil::read_file(const std::filesystem::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file.is_open()) {
        return "";
    }

    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

bool APPathUtil::write_file(const std::filesystem::path& path, const std::string& content) {
    // Ensure parent directory exists
    ensure_directory_exists(path.parent_path());

    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file.is_open()) {
        return false;
    }

    file << content;
    return file.good();
}

// =============================================================================
// Current Mod Folder Discovery via debug.getinfo
// =============================================================================

std::filesystem::path APPathUtil::discover_current_mod_folder(lua_State* L) {
    if (!L) {
        return {};
    }

    sol::state_view lua(L);

    try {
        // Execute: debug.getinfo(level, "S").source
        sol::table debug_table = lua["debug"];
        sol::protected_function getinfo = debug_table["getinfo"];

        // Try different stack levels to find the calling script
        for (int level = 2; level <= 10; ++level) {
            auto result = getinfo(level, "S");
            if (!result.valid()) continue;

            sol::table info = result;
            sol::optional<std::string> source = info["source"];

            if (source && source->length() > 1 && (*source)[0] == '@') {
                std::string path = source->substr(1); // Remove leading @
                std::filesystem::path script_path(path);

                // Script should be in <ModFolder>/Scripts/main.lua
                // So mod folder is script_path.parent_path().parent_path()
                if (script_path.has_parent_path()) {
                    auto scripts_folder = script_path.parent_path();
                    if (scripts_folder.filename() == "Scripts" && scripts_folder.has_parent_path()) {
                        return scripts_folder.parent_path();
                    }
                }
            }
        }
    } catch (...) {
        // Fallback handled by caller
    }

    return {};
}

} // namespace ap::client
