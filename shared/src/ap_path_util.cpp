#include "ap_path_util.h"
#include "ap_manager_base.h"

#include <fstream>
#include <sol/sol.hpp>
#include <sstream>

#ifdef _WIN32
#include <Windows.h>

extern "C" IMAGE_DOS_HEADER __ImageBase;
#endif

namespace ap
{

// =============================================================================
// Singleton Implementation
// =============================================================================

APPathUtil::APPathUtil(ConstructorKey)
{
    // Get DLL directory immediately (needed for fallback)
    cached_dll_directory_ = get_dll_directory();
}

APPathUtil *APPathUtil::get()
{
    static std::unique_ptr<APPathUtil> instance = std::make_unique<APPathUtil>(ConstructorKey{});
    return instance.get();
}

// =============================================================================
// Cache Management
// =============================================================================

void APPathUtil::initialize_cache()
{
    if (cache_initialized_)
    {
        return;
    }

    // Strategy 1: Try debug.getinfo via APManagerAccessor
    if (try_init_from_lua())
    {
        cache_initialized_ = true;
        return;
    }

    // Strategy 2: Fallback to DLL-relative search
    if (try_init_from_dll())
    {
        cache_initialized_ = true;
        return;
    }

    // Both failed - cache is still considered initialized (with empty values)
    cache_initialized_ = true;
}

void APPathUtil::clear_cache()
{
    cache_initialized_ = false;
    cached_ue4ss_folder_.reset();
    cached_mods_folder_.reset();
    cached_framework_folder_.reset();
}

void APPathUtil::reinitialize_cache()
{
    clear_cache();
    initialize_cache();
}

bool APPathUtil::try_init_from_lua()
{
    auto *manager = APManagerAccessor::get();
    if (!manager)
    {
        return false;
    }

    sol::state_view *lua = manager->get_cached_lua();
    if (!lua)
    {
        return false;
    }

    try
    {
        // Use debug.getinfo to find the source file path
        // We look at the manager's source file location to find the mod folder
        sol::table debug_table = (*lua)["debug"];
        if (!debug_table.valid())
        {
            return false;
        }

        sol::function getinfo = debug_table["getinfo"];
        if (!getinfo.valid())
        {
            return false;
        }

        // Get info about the current function's source
        // Level 0 = getinfo itself, level 1 = this C++ function, level 2+ = Lua caller
        sol::table info = getinfo(2, "S");
        if (!info.valid())
        {
            return false;
        }

        sol::optional<std::string> source = info["source"];
        if (!source || source->empty())
        {
            return false;
        }

        std::string source_path = *source;
        // Remove leading '@' if present (indicates file path)
        if (!source_path.empty() && source_path[0] == '@')
        {
            source_path = source_path.substr(1);
        }

        std::filesystem::path script_path(source_path);
        if (!script_path.is_absolute())
        {
            return false;
        }

        // Navigate up from script path to find Mods folder
        // Expected structure: .../Mods/<ModFolder>/Scripts/main.lua
        std::filesystem::path current = script_path.parent_path(); // Scripts
        current = current.parent_path();                           // ModFolder
        std::filesystem::path mod_folder = current;
        current = current.parent_path(); // Mods

        if (current.filename() == "Mods" && directory_exists(current))
        {
            cached_mods_folder_ = current;
            cached_ue4ss_folder_ = current.parent_path();

            // Find framework mod by content
            find_framework_mod_by_content();

            return true;
        }

        return false;
    }
    catch (...)
    {
        return false;
    }
}

bool APPathUtil::try_init_from_dll()
{
    if (cached_dll_directory_.empty())
    {
        return false;
    }

    // Search upward from DLL location for "ue4ss" folder
    // Expected structure: <game>/Binaries/Win64/ue4ss/Mods/<ModFolder>/Scripts/APFrameworkCore.dll
    // Or: <game>/Binaries/Win64/ue4ss/Mods/<ModFolder>/APFrameworkCore.dll

    std::filesystem::path search_path = cached_dll_directory_;
    for (int i = 0; i < 6 && !search_path.empty(); ++i)
    {
        if (search_path.filename() == "ue4ss")
        {
            cached_ue4ss_folder_ = search_path;

            std::filesystem::path mods_path = search_path / "Mods";
            if (directory_exists(mods_path))
            {
                cached_mods_folder_ = mods_path;
            }
            break;
        }
        search_path = search_path.parent_path();
    }

    // Find framework mod by content
    find_framework_mod_by_content();

    return cached_ue4ss_folder_.has_value();
}

bool APPathUtil::find_framework_mod_by_content()
{
    if (!cached_mods_folder_ || !directory_exists(*cached_mods_folder_))
    {
        return false;
    }

    std::error_code ec;
    for (const auto &entry : std::filesystem::directory_iterator(*cached_mods_folder_, ec))
    {
        if (ec || !entry.is_directory())
        {
            continue;
        }

        // Framework mod must contain both framework_config.json AND manifest.json
        auto config_path = entry.path() / "framework_config.json";
        auto manifest_path = entry.path() / "manifest.json";

        if (file_exists(config_path) && file_exists(manifest_path))
        {
            cached_framework_folder_ = entry.path();
            return true;
        }
    }

    return false;
}

std::filesystem::path APPathUtil::get_dll_directory() const
{
#ifdef _WIN32
    wchar_t dll_path[MAX_PATH];
    HMODULE hModule = reinterpret_cast<HMODULE>(&__ImageBase);
    DWORD len = GetModuleFileNameW(hModule, dll_path, MAX_PATH);

    if (len > 0 && len < MAX_PATH)
    {
        return std::filesystem::path(dll_path).parent_path();
    }
#endif
    return {};
}

// =============================================================================
// Discovery Methods
// =============================================================================

std::optional<std::filesystem::path> APPathUtil::find_ue4ss_folder()
{
    initialize_cache();
    return cached_ue4ss_folder_;
}

std::optional<std::filesystem::path> APPathUtil::find_mods_folder()
{
    initialize_cache();
    return cached_mods_folder_;
}

std::optional<std::filesystem::path> APPathUtil::find_framework_mod_folder()
{
    initialize_cache();
    return cached_framework_folder_;
}

std::optional<std::filesystem::path> APPathUtil::find_output_folder()
{
    auto framework_folder = find_framework_mod_folder();
    if (!framework_folder)
    {
        return std::nullopt;
    }

    std::filesystem::path output = *framework_folder / "output";
    ensure_directory_exists(output);
    return output;
}

std::optional<std::filesystem::path> APPathUtil::find_current_mod_folder(int level)
{
    auto *manager = APManagerAccessor::get();
    if (!manager)
    {
        return std::nullopt;
    }

    sol::state_view *lua = manager->get_cached_lua();
    if (!lua)
    {
        return std::nullopt;
    }

    try
    {
        sol::table debug_table = (*lua)["debug"];
        if (!debug_table.valid())
        {
            return std::nullopt;
        }

        sol::function getinfo = debug_table["getinfo"];
        if (!getinfo.valid())
        {
            return std::nullopt;
        }

        sol::table info = getinfo(level, "S");
        if (!info.valid())
        {
            return std::nullopt;
        }

        sol::optional<std::string> source = info["source"];
        if (!source || source->empty())
        {
            return std::nullopt;
        }

        std::string source_path = *source;
        if (!source_path.empty() && source_path[0] == '@')
        {
            source_path = source_path.substr(1);
        }

        std::filesystem::path script_path(source_path);
        if (!script_path.is_absolute())
        {
            return std::nullopt;
        }

        // Navigate up: .../Mods/<ModFolder>/Scripts/main.lua -> <ModFolder>
        std::filesystem::path current = script_path.parent_path(); // Scripts
        current = current.parent_path();                           // ModFolder

        if (directory_exists(current))
        {
            return current;
        }

        return std::nullopt;
    }
    catch (...)
    {
        return std::nullopt;
    }
}

// =============================================================================
// Well-Known Paths
// =============================================================================

std::filesystem::path APPathUtil::get_log_path()
{
    auto framework_folder = find_framework_mod_folder();
    if (framework_folder)
    {
        return *framework_folder / "ap_framework.log";
    }

    // Fallback to DLL directory
    return cached_dll_directory_ / "ap_framework.log";
}

std::filesystem::path APPathUtil::get_config_path()
{
    auto framework_folder = find_framework_mod_folder();
    if (framework_folder)
    {
        return *framework_folder / "framework_config.json";
    }

    // Fallback to DLL directory
    return cached_dll_directory_ / "framework_config.json";
}

std::filesystem::path APPathUtil::get_session_state_path()
{
    auto framework_folder = find_framework_mod_folder();
    if (framework_folder)
    {
        return *framework_folder / "session_state.json";
    }

    // Fallback to DLL directory
    return cached_dll_directory_ / "session_state.json";
}

// =============================================================================
// Path Queries
// =============================================================================

bool APPathUtil::file_exists(const std::filesystem::path &path) const
{
    std::error_code ec;
    return std::filesystem::is_regular_file(path, ec) && !ec;
}

bool APPathUtil::directory_exists(const std::filesystem::path &path) const
{
    std::error_code ec;
    return std::filesystem::is_directory(path, ec) && !ec;
}

// =============================================================================
// File Operations
// =============================================================================

std::string APPathUtil::read_file(const std::filesystem::path &path) const
{
    std::ifstream file(path, std::ios::binary);
    if (!file.is_open())
    {
        return "";
    }

    std::stringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

bool APPathUtil::write_file(const std::filesystem::path &path, const std::string &content) const
{
    // Ensure parent directory exists
    ensure_directory_exists(path.parent_path());

    std::ofstream file(path, std::ios::binary | std::ios::trunc);
    if (!file.is_open())
    {
        return false;
    }

    file << content;
    return file.good();
}

bool APPathUtil::ensure_directory_exists(const std::filesystem::path &path) const
{
    if (directory_exists(path))
    {
        return true;
    }

    std::error_code ec;
    return std::filesystem::create_directories(path, ec) && !ec;
}

} // namespace ap