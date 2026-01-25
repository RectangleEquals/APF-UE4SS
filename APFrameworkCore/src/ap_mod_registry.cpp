#include "ap_mod_registry.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <nlohmann/json.hpp>
#include <regex>
#include <mutex>

namespace ap {

class APModRegistry::Impl {
public:
    size_t discover_manifests(const std::filesystem::path& mods_folder) {
        std::lock_guard<std::mutex> lock(mutex_);

        if (!APPathUtil::directory_exists(mods_folder)) {
            APLogger::instance().log(LogLevel::Warn,
                "Mods folder not found: " + mods_folder.string());
            return 0;
        }

        size_t count = 0;
        std::error_code ec;

        for (const auto& entry : std::filesystem::directory_iterator(mods_folder, ec)) {
            if (!entry.is_directory(ec)) {
                continue;
            }

            // Look for manifest.json in each mod folder
            auto manifest_path = entry.path() / "manifest.json";
            if (!APPathUtil::file_exists(manifest_path)) {
                continue;
            }

            auto manifest = APModRegistry::parse_manifest_file(manifest_path);
            if (!manifest) {
                APLogger::instance().log(LogLevel::Warn,
                    "Failed to parse manifest: " + manifest_path.string());
                continue;
            }

            // Skip if mod_id already exists
            if (manifests_.find(manifest->mod_id) != manifests_.end()) {
                APLogger::instance().log(LogLevel::Warn,
                    "Duplicate mod_id: " + manifest->mod_id);
                continue;
            }

            APLogger::instance().log(LogLevel::Debug,
                "Discovered mod: " + manifest->mod_id +
                " v" + manifest->version +
                (manifest->enabled ? "" : " (disabled)"));

            manifests_[manifest->mod_id] = *manifest;
            count++;
        }

        APLogger::instance().log(LogLevel::Info,
            "Discovered " + std::to_string(count) + " mods");

        return count;
    }

    bool add_manifest(const Manifest& manifest) {
        std::lock_guard<std::mutex> lock(mutex_);

        if (manifests_.find(manifest.mod_id) != manifests_.end()) {
            return false;
        }

        manifests_[manifest.mod_id] = manifest;
        return true;
    }

    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        manifests_.clear();
        registered_.clear();
    }

    bool mark_registered(const std::string& mod_id) {
        std::lock_guard<std::mutex> lock(mutex_);

        if (manifests_.find(mod_id) == manifests_.end()) {
            return false;
        }

        registered_.insert(mod_id);

        APLogger::instance().log(LogLevel::Debug,
            "Mod registered: " + mod_id);

        return true;
    }

    bool is_registered(const std::string& mod_id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        return registered_.find(mod_id) != registered_.end();
    }

    bool all_registered() const {
        std::lock_guard<std::mutex> lock(mutex_);

        for (const auto& [mod_id, manifest] : manifests_) {
            if (manifest.enabled && registered_.find(mod_id) == registered_.end()) {
                return false;
            }
        }
        return true;
    }

    std::vector<std::string> get_pending_registrations() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<std::string> pending;

        for (const auto& [mod_id, manifest] : manifests_) {
            if (manifest.enabled && registered_.find(mod_id) == registered_.end()) {
                pending.push_back(mod_id);
            }
        }

        return pending;
    }

    void reset_registrations() {
        std::lock_guard<std::mutex> lock(mutex_);
        registered_.clear();
    }

    std::vector<Manifest> get_discovered_manifests() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<Manifest> result;
        result.reserve(manifests_.size());

        for (const auto& [mod_id, manifest] : manifests_) {
            result.push_back(manifest);
        }

        return result;
    }

    std::vector<Manifest> get_enabled_manifests() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<Manifest> result;

        for (const auto& [mod_id, manifest] : manifests_) {
            if (manifest.enabled) {
                result.push_back(manifest);
            }
        }

        return result;
    }

    std::optional<Manifest> get_manifest(const std::string& mod_id) const {
        std::lock_guard<std::mutex> lock(mutex_);

        auto it = manifests_.find(mod_id);
        if (it != manifests_.end()) {
            return it->second;
        }
        return std::nullopt;
    }

    ModType get_mod_type(const std::string& mod_id) const {
        // Priority clients match pattern: archipelago.<game>.*
        static const std::regex priority_pattern(R"(^archipelago\.[^.]+\..*)");
        if (std::regex_match(mod_id, priority_pattern)) {
            return ModType::Priority;
        }
        return ModType::Regular;
    }

    bool is_priority_client(const std::string& mod_id) const {
        return get_mod_type(mod_id) == ModType::Priority;
    }

    std::vector<std::string> get_priority_clients() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<std::string> result;

        for (const auto& [mod_id, manifest] : manifests_) {
            if (manifest.enabled && is_priority_client(mod_id)) {
                result.push_back(mod_id);
            }
        }

        return result;
    }

    std::vector<std::string> get_regular_mods() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<std::string> result;

        for (const auto& [mod_id, manifest] : manifests_) {
            if (manifest.enabled && !is_priority_client(mod_id)) {
                result.push_back(mod_id);
            }
        }

        return result;
    }

    std::vector<ModInfo> get_mod_infos() const {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<ModInfo> result;
        result.reserve(manifests_.size());

        for (const auto& [mod_id, manifest] : manifests_) {
            ModInfo info;
            info.mod_id = mod_id;
            info.name = manifest.name;
            info.version = manifest.version;
            info.type = get_mod_type(mod_id);
            info.is_registered = (registered_.find(mod_id) != registered_.end());
            info.has_conflict = false;  // Set later by APCapabilities
            result.push_back(info);
        }

        return result;
    }

    size_t count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return manifests_.size();
    }

private:
    mutable std::mutex mutex_;
    std::unordered_map<std::string, Manifest> manifests_;
    std::unordered_set<std::string> registered_;
};

// =============================================================================
// Static Parsing Functions
// =============================================================================

std::optional<Manifest> APModRegistry::parse_manifest(const std::string& json_content) {
    try {
        nlohmann::json j = nlohmann::json::parse(json_content);

        Manifest manifest;

        // Required fields
        if (!j.contains("mod_id") || !j["mod_id"].is_string()) {
            return std::nullopt;
        }
        manifest.mod_id = j["mod_id"].get<std::string>();

        manifest.name = j.value("name", manifest.mod_id);
        manifest.version = j.value("version", "1.0.0");
        manifest.enabled = j.value("enabled", true);
        manifest.description = j.value("description", "");

        // Parse incompatibility rules
        if (j.contains("incompatible") && j["incompatible"].is_array()) {
            for (const auto& rule : j["incompatible"]) {
                IncompatibilityRule inc;
                inc.id = rule.value("id", "");
                if (rule.contains("versions") && rule["versions"].is_array()) {
                    for (const auto& ver : rule["versions"]) {
                        inc.versions.push_back(ver.get<std::string>());
                    }
                }
                manifest.incompatible.push_back(inc);
            }
        }

        // Parse capabilities section
        if (j.contains("capabilities") && j["capabilities"].is_object()) {
            const auto& caps = j["capabilities"];

            // Parse locations
            if (caps.contains("locations") && caps["locations"].is_array()) {
                for (const auto& loc : caps["locations"]) {
                    LocationDef def;
                    def.name = loc.value("name", "");
                    def.amount = loc.value("amount", 1);
                    def.unique = loc.value("unique", false);

                    if (!def.name.empty()) {
                        manifest.locations.push_back(def);
                    }
                }
            }

            // Parse items
            if (caps.contains("items") && caps["items"].is_array()) {
                for (const auto& item : caps["items"]) {
                    ItemDef def;
                    def.name = item.value("name", "");
                    def.type = item_type_from_string(item.value("type", "filler"));
                    def.amount = item.value("amount", 1);
                    def.action = item.value("action", "");

                    // Parse action args
                    if (item.contains("args") && item["args"].is_array()) {
                        for (const auto& arg : item["args"]) {
                            ActionArg aa;
                            aa.name = arg.value("name", "");
                            aa.type = arg_type_from_string(arg.value("type", "string"));
                            if (arg.contains("value")) {
                                aa.value = arg["value"];
                            }
                            def.args.push_back(aa);
                        }
                    }

                    if (!def.name.empty()) {
                        manifest.items.push_back(def);
                    }
                }
            }
        }

        return manifest;

    } catch (const nlohmann::json::exception& e) {
        APLogger::instance().log(LogLevel::Error,
            "JSON parse error: " + std::string(e.what()));
        return std::nullopt;
    }
}

std::optional<Manifest> APModRegistry::parse_manifest_file(const std::filesystem::path& file_path) {
    std::string content = APPathUtil::read_file(file_path);
    if (content.empty()) {
        return std::nullopt;
    }
    return parse_manifest(content);
}

// =============================================================================
// Public API
// =============================================================================

APModRegistry::APModRegistry() : impl_(std::make_unique<Impl>()) {}
APModRegistry::~APModRegistry() = default;

size_t APModRegistry::discover_manifests(const std::filesystem::path& mods_folder) {
    return impl_->discover_manifests(mods_folder);
}

bool APModRegistry::add_manifest(const Manifest& manifest) {
    return impl_->add_manifest(manifest);
}

void APModRegistry::clear() {
    impl_->clear();
}

bool APModRegistry::mark_registered(const std::string& mod_id) {
    return impl_->mark_registered(mod_id);
}

bool APModRegistry::is_registered(const std::string& mod_id) const {
    return impl_->is_registered(mod_id);
}

bool APModRegistry::all_registered() const {
    return impl_->all_registered();
}

std::vector<std::string> APModRegistry::get_pending_registrations() const {
    return impl_->get_pending_registrations();
}

void APModRegistry::reset_registrations() {
    impl_->reset_registrations();
}

std::vector<Manifest> APModRegistry::get_discovered_manifests() const {
    return impl_->get_discovered_manifests();
}

std::vector<Manifest> APModRegistry::get_enabled_manifests() const {
    return impl_->get_enabled_manifests();
}

std::optional<Manifest> APModRegistry::get_manifest(const std::string& mod_id) const {
    return impl_->get_manifest(mod_id);
}

ModType APModRegistry::get_mod_type(const std::string& mod_id) const {
    return impl_->get_mod_type(mod_id);
}

bool APModRegistry::is_priority_client(const std::string& mod_id) const {
    return impl_->is_priority_client(mod_id);
}

std::vector<std::string> APModRegistry::get_priority_clients() const {
    return impl_->get_priority_clients();
}

std::vector<std::string> APModRegistry::get_regular_mods() const {
    return impl_->get_regular_mods();
}

std::vector<ModInfo> APModRegistry::get_mod_infos() const {
    return impl_->get_mod_infos();
}

size_t APModRegistry::count() const {
    return impl_->count();
}

} // namespace ap
