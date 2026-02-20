#include "ap_manifest.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <nlohmann/json.hpp>
#include <algorithm>
#include <set>

namespace ap {

// =============================================================================
// Loading
// =============================================================================

bool APManifest::load(const std::filesystem::path& mod_folder) {
    mod_folder_ = mod_folder;
    manifest_ = Manifest{};  // Reset to defaults
    loaded_ = false;

    std::filesystem::path manifest_path = mod_folder / "manifest.json";
    APLogger::get()->log(LogLevel::Trace, "APManifest", "Loading manifest from: " + manifest_path.string());

    std::string content = APPathUtil::get()->read_file(manifest_path);
    if (content.empty()) {
        APLogger::get()->log(LogLevel::Warn, "APManifest", "Manifest file empty or not found: " + manifest_path.string());
        return false;
    }

    try {
        nlohmann::json j = nlohmann::json::parse(content);

        // Required fields
        if (!j.contains("mod_id") || !j["mod_id"].is_string()) {
            return false;
        }
        manifest_.mod_id = j["mod_id"].get<std::string>();

        // Optional fields with defaults
        manifest_.name = j.value("name", manifest_.mod_id);
        manifest_.version = j.value("version", "1.0.0");
        manifest_.enabled = j.value("enabled", true);
        manifest_.description = j.value("description", "");

        // Incompatibility rules
        if (j.contains("incompatible") && j["incompatible"].is_array()) {
            for (const auto& inc : j["incompatible"]) {
                IncompatibilityRule rule;
                rule.id = inc.value("id", "");
                if (inc.contains("versions") && inc["versions"].is_array()) {
                    for (const auto& v : inc["versions"]) {
                        rule.versions.push_back(v.get<std::string>());
                    }
                }
                manifest_.incompatible.push_back(rule);
            }
        }

        // Locations
        if (j.contains("locations") && j["locations"].is_array()) {
            for (const auto& loc : j["locations"]) {
                LocationDef def;
                def.name = loc.value("name", "");
                def.amount = loc.value("amount", 1);
                def.region = loc.value("region", "");
                def.logic = loc.value("logic", "");
                def.requires_option = loc.value("requires_option", "");
                if (!def.name.empty()) {
                    manifest_.locations.push_back(def);
                }
            }
        }

        // Items
        if (j.contains("items") && j["items"].is_array()) {
            for (const auto& item : j["items"]) {
                ItemDef def;
                def.name = item.value("name", "");
                def.amount = item.value("amount", 1);
                def.action = item.value("action", "");

                // Item type
                std::string type_str = item.value("type", "filler");
                def.type = item_type_from_string(type_str);

                // Action args
                if (item.contains("args") && item["args"].is_array()) {
                    for (const auto& arg : item["args"]) {
                        ActionArg a;
                        a.name = arg.value("name", "");
                        std::string arg_type = arg.value("type", "string");
                        a.type = arg_type_from_string(arg_type);
                        if (arg.contains("value")) {
                            a.value = arg["value"];
                        }
                        def.args.push_back(a);
                    }
                }

                if (!def.name.empty()) {
                    manifest_.items.push_back(def);
                }
            }
        }

        loaded_ = true;
        APLogger::get()->log(LogLevel::Debug, "APManifest",
                             "Loaded manifest: mod_id=" + manifest_.mod_id + " name=" + manifest_.name +
                                 " version=" + manifest_.version);
        return true;
    } catch (const nlohmann::json::exception& e) {
        APLogger::get()->log(LogLevel::Error, "APManifest",
                             "JSON parse error in manifest: " + std::string(e.what()));
        return false;
    }
}

bool APManifest::load_current() {
    APLogger::get()->log(LogLevel::Trace, "APManifest", "load_current() called");

    auto mod_folder = APPathUtil::get()->find_current_mod_folder();
    if (!mod_folder) {
        APLogger::get()->log(LogLevel::Trace, "APManifest",
                             "find_current_mod_folder() returned nullopt - cannot load manifest");
        return false;
    }

    APLogger::get()->log(LogLevel::Trace, "APManifest",
                         "find_current_mod_folder() returned: " + mod_folder->string());

    bool result = load(*mod_folder);
    if (result) {
        APLogger::get()->log(LogLevel::Debug, "APManifest",
                             "load_current() succeeded: mod_id=" + manifest_.mod_id);
    } else {
        APLogger::get()->log(LogLevel::Warn, "APManifest",
                             "load_current() failed for folder: " + mod_folder->string());
    }
    return result;
}

// =============================================================================
// Path Accessors
// =============================================================================

std::filesystem::path APManifest::get_manifest_path() const {
    if (mod_folder_.empty()) {
        return {};
    }
    return mod_folder_ / "manifest.json";
}

// =============================================================================
// Manifest Accessors
// =============================================================================

std::vector<std::string> APManifest::get_action_names() const {
    std::set<std::string> unique_actions;
    for (const auto& item : manifest_.items) {
        if (!item.action.empty()) {
            unique_actions.insert(item.action);
        }
    }
    return std::vector<std::string>(unique_actions.begin(), unique_actions.end());
}

} // namespace ap