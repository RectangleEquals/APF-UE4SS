#include "ap_polling_thread.h"
#include "ap_client.h"
#include "ap_logger.h"

#include <chrono>

namespace ap
{

// =============================================================================
// Public API
// =============================================================================

APPollingThread::APPollingThread()
{
    // Default initialization
}

APPollingThread::~APPollingThread()
{
    stop(5000);
}

bool APPollingThread::start(int interval_ms)
{
    if (running_)
    {
        return false;
    }

    interval_ms_ = interval_ms;
    stop_token_.reset();
    running_ = true;

    // Set up client callbacks to queue events
    setup_client_callbacks();

    // Start polling thread
    thread_ = std::thread(&APPollingThread::thread_func, this);

    APLogger::get()->log(LogLevel::Info, "Polling thread started with " + std::to_string(interval_ms) + "ms interval");

    return true;
}

bool APPollingThread::stop(int timeout_ms)
{
    if (!running_)
    {
        return true;
    }

    running_ = false;
    stop_token_.request_stop();

    if (thread_.joinable())
    {
        // Wait for thread with timeout
        auto start = std::chrono::steady_clock::now();
        while (thread_.joinable())
        {
            auto elapsed =
                std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now() - start).count();

            if (elapsed >= timeout_ms)
            {
                APLogger::get()->log(LogLevel::Warn, "Polling thread stop timeout exceeded");
                return false;
            }

            // Try to join with short timeout
            std::this_thread::sleep_for(std::chrono::milliseconds(10));

            // Check if thread finished
            if (!running_)
            {
                thread_.join();
                break;
            }
        }
    }

    APLogger::get()->log(LogLevel::Info, "Polling thread stopped");
    return true;
}

bool APPollingThread::is_running() const
{
    return running_;
}

std::vector<FrameworkEvent> APPollingThread::get_events()
{
    return event_queue_.pop_all();
}

void APPollingThread::process_events(EventHandler handler)
{
    auto events = event_queue_.pop_all();
    for (const auto &event : events)
    {
        handler(event);
    }
}

void APPollingThread::set_interval(int interval_ms)
{
    interval_ms_ = interval_ms;
}

int APPollingThread::get_interval() const
{
    return interval_ms_;
}

EventQueue &APPollingThread::get_event_queue()
{
    return event_queue_;
}

// =============================================================================
// Private Methods
// =============================================================================

void APPollingThread::thread_func()
{
    APLogger::set_thread_name("AP-Polling");

    while (running_ && !stop_token_.stop_requested())
    {
        auto start = std::chrono::steady_clock::now();

        // Poll the AP client singleton
        try
        {
            APArchipelagoClient::get()->poll();
        }
        catch (const std::exception &e)
        {
            APLogger::get()->log(LogLevel::Error, "Exception in AP poll: " + std::string(e.what()));
        }

        // Sleep for remaining interval
        auto elapsed = std::chrono::steady_clock::now() - start;
        auto sleep_time = std::chrono::milliseconds(interval_ms_.load()) - elapsed;

        if (sleep_time > std::chrono::milliseconds(0))
        {
            stop_token_.sleep_for(sleep_time);
        }
    }

    running_ = false;
}

void APPollingThread::setup_client_callbacks()
{
    auto *client = APArchipelagoClient::get();

    // Item received
    client->set_item_received_callback([this](const ReceivedItem &item) {
        ItemReceivedEvent event;
        event.item_id = item.item_id;
        event.item_name = item.item_name;
        event.sender = item.player_name;
        event.location_id = item.location_id;
        event.is_self = (item.player_id == APArchipelagoClient::get()->get_player_number());

        event_queue_.push(event);
    });

    // Location scouted
    client->set_location_scouted_callback([this](const std::vector<ScoutResult> &results) {
        for (const auto &result : results)
        {
            LocationScoutEvent event;
            event.location_id = result.location_id;
            event.location_name = APArchipelagoClient::get()->get_location_name(result.location_id);
            event.item_id = result.item_id;
            event.item_name = result.item_name;
            event.player_name = result.player_name;

            event_queue_.push(event);
        }
    });

    // Slot connected
    client->set_slot_connected_callback([this](const SlotInfo &info) {
        LifecycleEvent event;
        event.old_state = LifecycleState::CONNECTING;
        event.new_state = LifecycleState::SYNCING;
        event.message = "Connected to slot: " + info.slot_name;

        event_queue_.push(event);
    });

    // Slot refused
    client->set_slot_refused_callback([this](const std::vector<std::string> &errors) {
        ErrorEvent event;
        event.code = ErrorCode::CONNECTION_FAILED;
        event.message = "Slot connection refused";

        if (!errors.empty())
        {
            event.details = errors[0];
            for (size_t i = 1; i < errors.size(); ++i)
            {
                event.details += "; " + errors[i];
            }
        }

        event_queue_.push(event);
    });

    // Disconnected
    client->set_disconnected_callback([this]() {
        LifecycleEvent event;
        event.old_state = LifecycleState::ACTIVE;
        event.new_state = LifecycleState::ERROR_STATE;
        event.message = "Disconnected from server";

        event_queue_.push(event);
    });

    // Print messages
    client->set_print_callback([this](const std::string &msg) {
        APMessageEvent event;
        event.type = "print";
        event.message = msg;

        event_queue_.push(event);
    });

    // Print JSON messages
    client->set_print_json_callback([this](const std::string &type, const nlohmann::json &data) {
        APMessageEvent event;
        event.type = type;
        event.data = data;

        // Try to extract message text
        if (data.is_array())
        {
            for (const auto &node : data)
            {
                if (node.contains("text"))
                {
                    event.message += node["text"].get<std::string>();
                }
            }
        }

        event_queue_.push(event);
    });

    // Bounced packets
    client->set_bounced_callback([this](const nlohmann::json &data) {
        APMessageEvent event;
        event.type = "bounced";
        event.data = data;

        event_queue_.push(event);
    });
}

} // namespace ap
