#include "ap_path_util.h"
#include "ap_logger.h"
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
        APLogger::get()->log(LogLevel::Trace, "APPathUtil", "Cache already initialized");
        return;
    }

    APLogger::get()->log(LogLevel::Trace, "APPathUtil", "Initializing path cache...");

    // Strategy 1: Try debug.getinfo via APManagerAccessor
    if (try_init_from_lua())
    {
        cache_initialized_ = true;
        APLogger::get()->log(LogLevel::Debug, "APPathUtil",
                             "Cache initialized via Lua debug.getinfo - mods: " +
                                 (cached_mods_folder_ ? cached_mods_folder_->string() : "(none)") +
                                 " framework: " +
                                 (cached_framework_folder_ ? cached_framework_folder_->string() : "(none)"));
        return;
    }

    APLogger::get()->log(LogLevel::Debug, "APPathUtil", "Lua init failed, trying DLL fallback");

    // Strategy 2: Fallback to DLL-relative search
    if (try_init_from_dll())
    {
        cache_initialized_ = true;
        APLogger::get()->log(LogLevel::Debug, "APPathUtil",
                             "Cache initialized via DLL fallback - mods: " +
                                 (cached_mods_folder_ ? cached_mods_folder_->string() : "(none)") +
                                 " framework: " +
                                 (cached_framework_folder_ ? cached_framework_folder_->string() : "(none)"));
        return;
    }

    // Both failed - cache is still considered initialized (with empty values)
    APLogger::get()->log(LogLevel::Warn, "APPathUtil", "Both Lua and DLL cache init strategies failed");
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
        APLogger::get()->log(LogLevel::Trace, "APPathUtil", "try_init_from_lua: no APManagerAccessor");
        return false;
    }

    sol::state_view *lua = manager->get_cached_lua();
    if (!lua)
    {
        APLogger::get()->log(LogLevel::Trace, "APPathUtil", "try_init_from_lua: no cached Lua state");
        return false;
    }

    try
    {
        // Use debug.getinfo to find the source file path
        // We look at the manager's source file location to find the mod folder
        sol::table debug_table = (*lua)["debug"];
        if (!debug_table.valid())
        {
            APLogger::get()->log(LogLevel::Trace, "APPathUtil", "try_init_from_lua: debug table not valid");
            return false;
        }

        sol::function getinfo = debug_table["getinfo"];
        if (!getinfo.valid())
        {
            APLogger::get()->log(LogLevel::Trace, "APPathUtil", "try_init_from_lua: debug.getinfo not valid");
            return false;
        }

        // Get info about the current function's source
        // Level 0 = getinfo itself, level 1 = this C++ function, level 2+ = Lua caller
        sol::table info = getinfo(2, "S");
        if (!info.valid())
        {
            APLogger::get()->log(LogLevel::Trace, "APPathUtil", "try_init_from_lua: getinfo(2, 'S') returned invalid");
            return false;
        }

        sol::optional<std::string> source = info["source"];
        if (!source || source->empty())
        {
            APLogger::get()->log(LogLevel::Trace, "APPathUtil", "try_init_from_lua: source is nil or empty");
            return false;
        }

        std::string source_path = *source;
        APLogger::get()->log(LogLevel::Trace, "APPathUtil", "try_init_from_lua: raw source = " + source_path);

        // Remove leading '@' if present (indicates file path)
        if (!source_path.empty() && source_path[0] == '@')
        {
            source_path = source_path.substr(1);
        }

        std::filesystem::path script_path(source_path);
        if (!script_path.is_absolute())
        {
            APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                                 "try_init_from_lua: path not absolute: " + source_path);
            return false;
        }

        // Navigate up from script path to find Mods folder
        // Expected structure: .../Mods/<ModFolder>/Scripts/main.lua
        std::filesystem::path current = script_path.parent_path(); // Scripts
        current = current.parent_path();                           // ModFolder
        current = current.parent_path();                           // Mods

        if (current.filename() == "Mods" && directory_exists(current))
        {
            cached_mods_folder_ = current;
            cached_ue4ss_folder_ = current.parent_path();

            APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                                 "try_init_from_lua: found Mods folder at " + current.string());

            // Find framework mod by content
            find_framework_mod_by_content();

            return true;
        }

        APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                             "try_init_from_lua: parent not 'Mods' or doesn't exist: " + current.string());
        return false;
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APPathUtil",
                             "try_init_from_lua: exception: " + std::string(e.what()));
        return false;
    }
    catch (...)
    {
        APLogger::get()->log(LogLevel::Error, "APPathUtil", "try_init_from_lua: unknown exception");
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
        APLogger::get()->log(LogLevel::Trace, "APPathUtil", "find_framework_mod_by_content: no mods folder");
        return false;
    }

    APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                         "find_framework_mod_by_content: scanning " + cached_mods_folder_->string());

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
            APLogger::get()->log(LogLevel::Debug, "APPathUtil",
                                 "Found framework mod at: " + entry.path().string());
            return true;
        }
    }

    APLogger::get()->log(LogLevel::Warn, "APPathUtil",
                         "No framework mod found in " + cached_mods_folder_->string());
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

std::optional<std::filesystem::path> APPathUtil::find_current_mod_folder()
{
    auto *manager = APManagerAccessor::get();
    if (!manager)
    {
        APLogger::get()->log(LogLevel::Trace, "APPathUtil", "find_current_mod_folder: no APManagerAccessor");
        return std::nullopt;
    }

    sol::state_view *lua = manager->get_cached_lua();
    if (!lua)
    {
        APLogger::get()->log(LogLevel::Trace, "APPathUtil", "find_current_mod_folder: no cached Lua state");
        return std::nullopt;
    }

    try
    {
        sol::table debug_table = (*lua)["debug"];
        if (!debug_table.valid())
        {
            APLogger::get()->log(LogLevel::Trace, "APPathUtil", "find_current_mod_folder: debug table not valid");
            return std::nullopt;
        }

        sol::function getinfo = debug_table["getinfo"];
        if (!getinfo.valid())
        {
            APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                                 "find_current_mod_folder: debug.getinfo not valid");
            return std::nullopt;
        }

        // Scan up the call stack to find the first Lua source file.
        // During require(), the stack has multiple C frames before the Lua caller,
        // so we can't use a fixed level — we scan until we find a non-C source.
        for (int level = 0; level <= 10; ++level)
        {
            sol::object result = getinfo(level, "S");
            if (!result.valid() || result.get_type() != sol::type::table)
            {
                break; // End of stack
            }

            sol::table info = result.as<sol::table>();
            sol::optional<std::string> source = info["source"];
            if (!source || source->empty() || *source == "=[C]")
            {
                continue; // Skip C functions
            }

            std::string source_path = *source;
            APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                                 "find_current_mod_folder: found Lua source at level " +
                                     std::to_string(level) + ": " + source_path);

            // Remove leading '@' if present (indicates file path)
            if (source_path[0] == '@')
            {
                source_path = source_path.substr(1);
            }

            std::filesystem::path script_path(source_path);
            if (!script_path.is_absolute())
            {
                APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                                     "find_current_mod_folder: path not absolute, skipping: " + source_path);
                continue; // Skip non-absolute paths, keep searching
            }

            // Navigate up: .../Mods/<ModFolder>/Scripts/main.lua -> <ModFolder>
            std::filesystem::path mod_folder = script_path.parent_path().parent_path();

            if (directory_exists(mod_folder))
            {
                APLogger::get()->log(LogLevel::Debug, "APPathUtil",
                                     "find_current_mod_folder: resolved to " + mod_folder.string());
                return mod_folder;
            }
        }

        APLogger::get()->log(LogLevel::Warn, "APPathUtil",
                             "find_current_mod_folder: no Lua source found in stack");
        return std::nullopt;
    }
    catch (const std::exception &e)
    {
        APLogger::get()->log(LogLevel::Error, "APPathUtil",
                             "find_current_mod_folder: exception: " + std::string(e.what()));
        return std::nullopt;
    }
    catch (...)
    {
        APLogger::get()->log(LogLevel::Error, "APPathUtil", "find_current_mod_folder: unknown exception");
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
    auto output_folder = find_output_folder();
    if (output_folder)
    {
        return *output_folder / "session_state.json";
    }

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