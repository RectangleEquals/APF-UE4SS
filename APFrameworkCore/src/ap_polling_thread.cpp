#include "ap_polling_thread.h"
#include "ap_logger.h"

#include <thread>
#include <atomic>
#include <chrono>

namespace ap {

class APPollingThread::Impl {
public:
    Impl() = default;

    ~Impl() {
        stop(5000);
    }

    bool start(APClient* client, int interval_ms) {
        if (running_) {
            return false;
        }

        if (!client) {
            return false;
        }

        client_ = client;
        interval_ms_ = interval_ms;
        stop_token_.reset();
        running_ = true;

        // Set up client callbacks to queue events
        setup_client_callbacks();

        // Start polling thread
        thread_ = std::thread(&Impl::thread_func, this);

        APLogger::instance().log(LogLevel::Info,
            "Polling thread started with " + std::to_string(interval_ms) + "ms interval");

        return true;
    }

    bool stop(int timeout_ms) {
        if (!running_) {
            return true;
        }

        running_ = false;
        stop_token_.request_stop();

        if (thread_.joinable()) {
            // Wait for thread with timeout
            auto start = std::chrono::steady_clock::now();
            while (thread_.joinable()) {
                auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now() - start).count();

                if (elapsed >= timeout_ms) {
                    APLogger::instance().log(LogLevel::Warn,
                        "Polling thread stop timeout exceeded");
                    return false;
                }

                // Try to join with short timeout
                std::this_thread::sleep_for(std::chrono::milliseconds(10));

                // Check if thread finished
                if (!running_) {
                    thread_.join();
                    break;
                }
            }
        }

        APLogger::instance().log(LogLevel::Info, "Polling thread stopped");
        return true;
    }

    bool is_running() const {
        return running_;
    }

    std::vector<FrameworkEvent> get_events() {
        return event_queue_.pop_all();
    }

    void process_events(EventHandler handler) {
        auto events = event_queue_.pop_all();
        for (const auto& event : events) {
            handler(event);
        }
    }

    void set_interval(int interval_ms) {
        interval_ms_ = interval_ms;
    }

    int get_interval() const {
        return interval_ms_;
    }

    EventQueue& get_event_queue() {
        return event_queue_;
    }

private:
    void thread_func() {
        APLogger::set_thread_name("AP-Polling");

        while (running_ && !stop_token_.stop_requested()) {
            auto start = std::chrono::steady_clock::now();

            // Poll the AP client
            if (client_) {
                try {
                    client_->poll();
                } catch (const std::exception& e) {
                    APLogger::instance().log(LogLevel::Error,
                        "Exception in AP poll: " + std::string(e.what()));
                }
            }

            // Sleep for remaining interval
            auto elapsed = std::chrono::steady_clock::now() - start;
            auto sleep_time = std::chrono::milliseconds(interval_ms_) - elapsed;

            if (sleep_time > std::chrono::milliseconds(0)) {
                stop_token_.sleep_for(sleep_time);
            }
        }

        running_ = false;
    }

    void setup_client_callbacks() {
        if (!client_) return;

        // Item received
        client_->set_item_received_callback([this](const ReceivedItem& item) {
            ItemReceivedEvent event;
            event.item_id = item.item_id;
            event.item_name = item.item_name;
            event.sender = item.player_name;
            event.location_id = item.location_id;
            event.is_self = (item.player_id == client_->get_player_number());

            event_queue_.push(event);
        });

        // Location scouted
        client_->set_location_scouted_callback([this](const std::vector<ScoutResult>& results) {
            for (const auto& result : results) {
                LocationScoutEvent event;
                event.location_id = result.location_id;
                event.location_name = client_->get_location_name(result.location_id);
                event.item_id = result.item_id;
                event.item_name = result.item_name;
                event.player_name = result.player_name;

                event_queue_.push(event);
            }
        });

        // Slot connected
        client_->set_slot_connected_callback([this](const SlotInfo& info) {
            LifecycleEvent event;
            event.old_state = LifecycleState::CONNECTING;
            event.new_state = LifecycleState::SYNCING;
            event.message = "Connected to slot: " + info.slot_name;

            event_queue_.push(event);
        });

        // Slot refused
        client_->set_slot_refused_callback([this](const std::vector<std::string>& errors) {
            ErrorEvent event;
            event.code = ErrorCode::CONNECTION_FAILED;
            event.message = "Slot connection refused";

            if (!errors.empty()) {
                event.details = errors[0];
                for (size_t i = 1; i < errors.size(); ++i) {
                    event.details += "; " + errors[i];
                }
            }

            event_queue_.push(event);
        });

        // Disconnected
        client_->set_disconnected_callback([this]() {
            LifecycleEvent event;
            event.old_state = LifecycleState::ACTIVE;
            event.new_state = LifecycleState::ERROR_STATE;
            event.message = "Disconnected from server";

            event_queue_.push(event);
        });

        // Print messages
        client_->set_print_callback([this](const std::string& msg) {
            APMessageEvent event;
            event.type = "print";
            event.message = msg;

            event_queue_.push(event);
        });

        // Print JSON messages
        client_->set_print_json_callback([this](const std::string& type, const nlohmann::json& data) {
            APMessageEvent event;
            event.type = type;
            event.data = data;

            // Try to extract message text
            if (data.is_array()) {
                for (const auto& node : data) {
                    if (node.contains("text")) {
                        event.message += node["text"].get<std::string>();
                    }
                }
            }

            event_queue_.push(event);
        });

        // Bounced packets
        client_->set_bounced_callback([this](const nlohmann::json& data) {
            APMessageEvent event;
            event.type = "bounced";
            event.data = data;

            event_queue_.push(event);
        });
    }

    APClient* client_ = nullptr;
    std::thread thread_;
    std::atomic<bool> running_{false};
    std::atomic<int> interval_ms_{16};
    StopToken stop_token_;
    EventQueue event_queue_;
};

// =============================================================================
// Public API
// =============================================================================

APPollingThread::APPollingThread() : impl_(std::make_unique<Impl>()) {}
APPollingThread::~APPollingThread() = default;

bool APPollingThread::start(APClient* client, int interval_ms) {
    return impl_->start(client, interval_ms);
}

bool APPollingThread::stop(int timeout_ms) {
    return impl_->stop(timeout_ms);
}

bool APPollingThread::is_running() const {
    return impl_->is_running();
}

std::vector<FrameworkEvent> APPollingThread::get_events() {
    return impl_->get_events();
}

void APPollingThread::process_events(EventHandler handler) {
    impl_->process_events(std::move(handler));
}

void APPollingThread::set_interval(int interval_ms) {
    impl_->set_interval(interval_ms);
}

int APPollingThread::get_interval() const {
    return impl_->get_interval();
}

EventQueue& APPollingThread::get_event_queue() {
    return impl_->get_event_queue();
}

} // namespace ap
