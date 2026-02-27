#include "ap_path_util.h"
#include "ap_logger.h"
#include "ap_manager_base.h"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <numeric>
#include <sol/sol.hpp>
#include <sstream>

#ifdef _WIN32
#include <cstring> // _stricmp
#else
#include <strings.h> // strcasecmp
#endif

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
    // Capture and normalize the DLL directory immediately — the fallback
    // strategy needs it before any Lua state exists.
    cached_dll_directory_ = normalize(get_dll_directory());
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
        script_path = normalize(script_path);
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

        if (iequal_component(current.filename().string(), "Mods") && directory_exists(current))
        {
            cached_mods_folder_ = normalize(current);
            cached_ue4ss_folder_ = normalize(current.parent_path());

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
        APLogger::get()->log(LogLevel::Trace, "APPathUtil", "try_init_from_dll: no DLL directory");
        return false;
    }

    APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                         "try_init_from_dll: searching from " + cached_dll_directory_.string());

    // Step 1: search for the ue4ss folder by pattern
    auto ue4ss_matches = find_by_pattern(cached_dll_directory_, "ue4ss");
    if (ue4ss_matches)
    {
        cached_ue4ss_folder_ = (*ue4ss_matches)[0];
        APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                             "try_init_from_dll: found ue4ss at " + cached_ue4ss_folder_->string());

        // Derive Mods path — explicit existence check since we constructed it
        std::filesystem::path mods_candidate = normalize(*cached_ue4ss_folder_ / "Mods");
        if (directory_exists(mods_candidate))
        {
            cached_mods_folder_ = mods_candidate;
        }
        else
        {
            APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                                 "try_init_from_dll: no Mods subfolder under " +
                                     cached_ue4ss_folder_->string());
        }
    }
    else
    {
        // Step 2 (graceful degradation): search for ue4ss/Mods directly in case
        // the ue4ss folder itself was renamed
        APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                             "try_init_from_dll: ue4ss not found, trying ue4ss/Mods pattern");
        auto mods_matches = find_by_pattern(cached_dll_directory_, "ue4ss/Mods");
        if (mods_matches)
        {
            cached_mods_folder_  = (*mods_matches)[0];
            cached_ue4ss_folder_ = normalize(cached_mods_folder_->parent_path());
            APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                                 "try_init_from_dll: found Mods at " + cached_mods_folder_->string());
        }
    }

    // Step 3: locate framework mod by content within the Mods folder
    find_framework_mod_by_content();

    return cached_mods_folder_.has_value();
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
            cached_framework_folder_ = normalize(entry.path());
            APLogger::get()->log(LogLevel::Debug, "APPathUtil",
                                 "Found framework mod at: " + cached_framework_folder_->string());
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
        return normalize(std::filesystem::path(dll_path).parent_path());
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
            script_path = normalize(script_path);
            if (!script_path.is_absolute())
            {
                APLogger::get()->log(LogLevel::Trace, "APPathUtil",
                                     "find_current_mod_folder: path not absolute, skipping: " + source_path);
                continue; // Skip non-absolute paths, keep searching
            }

            // Navigate up: .../Mods/<ModFolder>/Scripts/main.lua -> <ModFolder>
            std::filesystem::path mod_folder = normalize(script_path.parent_path().parent_path());

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

// =============================================================================
// Path helpers
// =============================================================================

std::filesystem::path APPathUtil::normalize(const std::filesystem::path& p) const
{
    return p.lexically_normal().make_preferred();
}

bool APPathUtil::iequal_component(const std::string& a, const std::string& b) const
{
#ifdef _WIN32
    return _stricmp(a.c_str(), b.c_str()) == 0;
#else
    return strcasecmp(a.c_str(), b.c_str()) == 0;
#endif
}

std::vector<std::string> APPathUtil::split_pattern(const std::string& pattern) const
{
    std::vector<std::string> components;
    std::stringstream ss(pattern);
    std::string token;
    while (std::getline(ss, token, '/'))
    {
        if (token.empty())
            continue;
        // Strip a leading "*" wildcard — it is always implied
        if (components.empty() && token == "*")
            continue;
        components.push_back(token);
    }
    return components;
}

std::vector<std::string> APPathUtil::split_components(const std::filesystem::path& p) const
{
    std::vector<std::string> components;
    for (const auto& part : p)
    {
        std::string s = part.string();
        // Skip root-name (e.g. "C:") and root-directory (e.g. "\", "/")
        if (s.empty() || s == "/" || s == "\\" || (s.size() == 2 && s[1] == ':'))
            continue;
        components.push_back(s);
    }
    return components;
}

bool APPathUtil::components_contain_pattern(const std::vector<std::string>& haystack,
                                            const std::vector<std::string>& needle,
                                            std::string& out_matched_subpath) const
{
    if (needle.empty() || needle.size() > haystack.size())
        return false;

    const std::size_t limit = haystack.size() - needle.size();
    for (std::size_t i = 0; i <= limit; ++i)
    {
        bool match = true;
        for (std::size_t j = 0; j < needle.size(); ++j)
        {
            if (!iequal_component(haystack[i + j], needle[j]))
            {
                match = false;
                break;
            }
        }
        if (match)
        {
            std::string sub;
            for (std::size_t j = 0; j < needle.size(); ++j)
            {
                if (j > 0) sub += '/';
                sub += haystack[i + j];
            }
            out_matched_subpath = std::move(sub);
            return true;
        }
    }
    return false;
}

int APPathUtil::levenshtein_distance(const std::string& a, const std::string& b) const
{
    const std::size_t m = a.size();
    const std::size_t n = b.size();
    std::vector<int> prev(n + 1), curr(n + 1);
    std::iota(prev.begin(), prev.end(), 0);
    for (std::size_t i = 1; i <= m; ++i)
    {
        curr[0] = static_cast<int>(i);
        for (std::size_t j = 1; j <= n; ++j)
        {
            const int cost = (std::tolower(static_cast<unsigned char>(a[i - 1])) ==
                              std::tolower(static_cast<unsigned char>(b[j - 1])))
                             ? 0 : 1;
            curr[j] = std::min({prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost});
        }
        std::swap(prev, curr);
    }
    return prev[n];
}

// =============================================================================
// Pattern-based search
// =============================================================================

std::optional<std::vector<std::filesystem::path>>
APPathUtil::find_by_pattern(const std::filesystem::path& search_root,
                             const std::string& pattern,
                             int max_depth) const
{
    const std::vector<std::string> needle = split_pattern(pattern);
    if (needle.empty())
        return std::nullopt;

    std::string pattern_stripped;
    for (std::size_t i = 0; i < needle.size(); ++i)
    {
        if (i > 0) pattern_stripped += '/';
        pattern_stripped += needle[i];
    }

    const int root_depth = static_cast<int>(
        split_components(normalize(search_root)).size());

    struct Match { std::filesystem::path path; int score; };
    std::vector<Match> matches;

    std::error_code ec;
    std::filesystem::recursive_directory_iterator it(
        search_root,
        std::filesystem::directory_options::skip_permission_denied,
        ec);

    if (ec)
    {
        APLogger::get()->log(LogLevel::Warn, "APPathUtil",
                             "find_by_pattern: cannot iterate " + search_root.string() +
                             " — " + ec.message());
        return std::nullopt;
    }

    for (; it != std::filesystem::recursive_directory_iterator(); it.increment(ec))
    {
        if (ec) { ec.clear(); it.disable_recursion_pending(); continue; }
        if (!it->is_directory()) continue;

        const std::filesystem::path candidate = normalize(it->path());
        const int entry_depth = static_cast<int>(split_components(candidate).size());
        if (entry_depth - root_depth > max_depth)
        {
            it.disable_recursion_pending();
            continue;
        }

        std::string matched_sub;
        if (components_contain_pattern(split_components(candidate), needle, matched_sub))
            matches.push_back({candidate, levenshtein_distance(pattern_stripped, matched_sub)});
    }

    if (matches.empty())
        return std::nullopt;

    std::stable_sort(matches.begin(), matches.end(),
                     [](const Match& a, const Match& b) { return a.score < b.score; });

    std::vector<std::filesystem::path> result;
    result.reserve(matches.size());
    for (auto& m : matches)
        result.push_back(std::move(m.path));
    return result;
}

// =============================================================================
// File Operations
// =============================================================================

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