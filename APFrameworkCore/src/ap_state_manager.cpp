#include "ap_state_manager.h"
#include "ap_logger.h"
#include "ap_path_util.h"

#include <nlohmann/json.hpp>
#include <mutex>
#include <chrono>

namespace ap {

class APStateManager::Impl {
public:
    bool save_state(const std::filesystem::path& path) {
        std::lock_guard<std::mutex> lock(mutex_);

        try {
            std::string json_content = state_.to_json().dump(2);
            if (APPathUtil::write_file(path, json_content)) {
                APLogger::instance().log(LogLevel::Debug,
                    "Saved session state to: " + path.string());
                return true;
            }
        } catch (const std::exception& e) {
            APLogger::instance().log(LogLevel::Error,
                "Failed to save session state: " + std::string(e.what()));
        }

        return false;
    }

    bool save_state() {
        return save_state(APPathUtil::get_session_state_path());
    }

    bool load_state(const std::filesystem::path& path) {
        std::lock_guard<std::mutex> lock(mutex_);

        std::string content = APPathUtil::read_file(path);
        if (content.empty()) {
            APLogger::instance().log(LogLevel::Debug,
                "No session state file found: " + path.string());
            return false;
        }

        try {
            nlohmann::json j = nlohmann::json::parse(content);
            state_ = SessionState::from_json(j);
            loaded_ = true;

            APLogger::instance().log(LogLevel::Info,
                "Loaded session state from: " + path.string() +
                " (item_index=" + std::to_string(state_.received_item_index) +
                ", locations=" + std::to_string(state_.checked_locations.size()) + ")");

            return true;

        } catch (const nlohmann::json::exception& e) {
            APLogger::instance().log(LogLevel::Error,
                "Failed to parse session state: " + std::string(e.what()));
            return false;
        }
    }

    bool load_state() {
        return load_state(APPathUtil::get_session_state_path());
    }

    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        state_ = SessionState{};
        loaded_ = false;
    }

    bool is_loaded() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return loaded_;
    }

    void set_received_item_index(int index) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.received_item_index = index;
    }

    int get_received_item_index() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.received_item_index;
    }

    int increment_received_item_index() {
        std::lock_guard<std::mutex> lock(mutex_);
        return ++state_.received_item_index;
    }

    void add_checked_location(int64_t location_id) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.checked_locations.insert(location_id);
    }

    bool is_location_checked(int64_t location_id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.checked_locations.find(location_id) != state_.checked_locations.end();
    }

    std::set<int64_t> get_checked_locations() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.checked_locations;
    }

    size_t get_checked_location_count() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.checked_locations.size();
    }

    void set_checked_locations(const std::set<int64_t>& locations) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.checked_locations = locations;
    }

    void set_item_progression_count(int64_t item_id, int count) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.item_progression_counts[item_id] = count;
    }

    int get_item_progression_count(int64_t item_id) const {
        std::lock_guard<std::mutex> lock(mutex_);
        auto it = state_.item_progression_counts.find(item_id);
        return (it != state_.item_progression_counts.end()) ? it->second : 0;
    }

    int increment_item_progression_count(int64_t item_id) {
        std::lock_guard<std::mutex> lock(mutex_);
        return ++state_.item_progression_counts[item_id];
    }

    std::map<int64_t, int> get_all_item_progression_counts() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.item_progression_counts;
    }

    void set_checksum(const std::string& checksum) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.checksum = checksum;
    }

    std::string get_checksum() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.checksum;
    }

    bool validate_checksum(const std::string& current_checksum) const {
        std::lock_guard<std::mutex> lock(mutex_);

        if (state_.checksum.empty()) {
            // No stored checksum - first run
            return true;
        }

        bool match = (state_.checksum == current_checksum);
        if (!match) {
            APLogger::instance().log(LogLevel::Error,
                "Checksum mismatch! Stored: " + state_.checksum +
                ", Current: " + current_checksum);
        }
        return match;
    }

    void set_slot_name(const std::string& slot_name) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.slot_name = slot_name;
    }

    std::string get_slot_name() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.slot_name;
    }

    void set_game_name(const std::string& game_name) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.game_name = game_name;
    }

    std::string get_game_name() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.game_name;
    }

    void set_server_info(const std::string& server, int port) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.ap_server = server;
        state_.ap_port = port;
    }

    std::string get_server() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.ap_server;
    }

    int get_port() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_.ap_port;
    }

    void touch() {
        std::lock_guard<std::mutex> lock(mutex_);
        state_.last_active = std::chrono::system_clock::now();
    }

    SessionState get_state() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return state_;
    }

    void set_state(const SessionState& state) {
        std::lock_guard<std::mutex> lock(mutex_);
        state_ = state;
        loaded_ = true;
    }

private:
    mutable std::mutex mutex_;
    SessionState state_;
    bool loaded_ = false;
};

// =============================================================================
// Public API
// =============================================================================

APStateManager::APStateManager() : impl_(std::make_unique<Impl>()) {}
APStateManager::~APStateManager() = default;

bool APStateManager::save_state(const std::filesystem::path& path) {
    return impl_->save_state(path);
}

bool APStateManager::save_state() {
    return impl_->save_state();
}

bool APStateManager::load_state(const std::filesystem::path& path) {
    return impl_->load_state(path);
}

bool APStateManager::load_state() {
    return impl_->load_state();
}

void APStateManager::clear() {
    impl_->clear();
}

bool APStateManager::is_loaded() const {
    return impl_->is_loaded();
}

void APStateManager::set_received_item_index(int index) {
    impl_->set_received_item_index(index);
}

int APStateManager::get_received_item_index() const {
    return impl_->get_received_item_index();
}

int APStateManager::increment_received_item_index() {
    return impl_->increment_received_item_index();
}

void APStateManager::add_checked_location(int64_t location_id) {
    impl_->add_checked_location(location_id);
}

bool APStateManager::is_location_checked(int64_t location_id) const {
    return impl_->is_location_checked(location_id);
}

std::set<int64_t> APStateManager::get_checked_locations() const {
    return impl_->get_checked_locations();
}

size_t APStateManager::get_checked_location_count() const {
    return impl_->get_checked_location_count();
}

void APStateManager::set_checked_locations(const std::set<int64_t>& locations) {
    impl_->set_checked_locations(locations);
}

void APStateManager::set_item_progression_count(int64_t item_id, int count) {
    impl_->set_item_progression_count(item_id, count);
}

int APStateManager::get_item_progression_count(int64_t item_id) const {
    return impl_->get_item_progression_count(item_id);
}

int APStateManager::increment_item_progression_count(int64_t item_id) {
    return impl_->increment_item_progression_count(item_id);
}

std::map<int64_t, int> APStateManager::get_all_item_progression_counts() const {
    return impl_->get_all_item_progression_counts();
}

void APStateManager::set_checksum(const std::string& checksum) {
    impl_->set_checksum(checksum);
}

std::string APStateManager::get_checksum() const {
    return impl_->get_checksum();
}

bool APStateManager::validate_checksum(const std::string& current_checksum) const {
    return impl_->validate_checksum(current_checksum);
}

void APStateManager::set_slot_name(const std::string& slot_name) {
    impl_->set_slot_name(slot_name);
}

std::string APStateManager::get_slot_name() const {
    return impl_->get_slot_name();
}

void APStateManager::set_game_name(const std::string& game_name) {
    impl_->set_game_name(game_name);
}

std::string APStateManager::get_game_name() const {
    return impl_->get_game_name();
}

void APStateManager::set_server_info(const std::string& server, int port) {
    impl_->set_server_info(server, port);
}

std::string APStateManager::get_server() const {
    return impl_->get_server();
}

int APStateManager::get_port() const {
    return impl_->get_port();
}

void APStateManager::touch() {
    impl_->touch();
}

SessionState APStateManager::get_state() const {
    return impl_->get_state();
}

void APStateManager::set_state(const SessionState& state) {
    impl_->set_state(state);
}

} // namespace ap
