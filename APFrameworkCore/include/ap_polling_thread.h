#pragma once

#include "ap_exports.h"
#include "message_queues.h"
#include "stop_token.h"

#include <atomic>
#include <functional>
#include <thread>

namespace ap
{

/**
 * @brief Background thread for polling the AP server.
 *
 * Runs APArchipelagoClient::poll() at a configurable interval and queues events
 * for processing on the main thread.
 *
 * Thread model:
 * - Polling thread calls APArchipelagoClient::get()->poll() at regular intervals
 * - Events from callbacks are queued in thread-safe queues
 * - Main thread retrieves events via get_events() or process_events()
 */
class AP_API APPollingThread
{
  public:
    using EventHandler = std::function<void(const FrameworkEvent &)>;

    APPollingThread();
    ~APPollingThread();

    // Delete copy/move
    APPollingThread(const APPollingThread &) = delete;
    APPollingThread &operator=(const APPollingThread &) = delete;
    APPollingThread(APPollingThread &&) = delete;
    APPollingThread &operator=(APPollingThread &&) = delete;

    /**
     * @brief Start the polling thread.
     * @param interval_ms Polling interval in milliseconds.
     * @return true if started successfully.
     */
    bool start(int interval_ms = 16);

    /**
     * @brief Stop the polling thread.
     * @param timeout_ms Maximum time to wait for thread to finish.
     * @return true if stopped within timeout.
     */
    bool stop(int timeout_ms = 5000);

    /**
     * @brief Check if the polling thread is running.
     * @return true if running.
     */
    bool is_running() const;

    /**
     * @brief Get all queued events.
     * @return Vector of events.
     *
     * Should be called from main thread.
     */
    std::vector<FrameworkEvent> get_events();

    /**
     * @brief Process all queued events with handler.
     * @param handler Function to call for each event.
     *
     * Should be called from main thread.
     */
    void process_events(EventHandler handler);

    /**
     * @brief Set the polling interval.
     * @param interval_ms New interval in milliseconds.
     */
    void set_interval(int interval_ms);

    /**
     * @brief Get the current polling interval.
     * @return Interval in milliseconds.
     */
    int get_interval() const;

    /**
     * @brief Get the event queue for direct access.
     * @return Reference to the event queue.
     */
    EventQueue &get_event_queue();

  private:
    // =========================================================================
    // Private Methods
    // =========================================================================
    void thread_func();
    void setup_client_callbacks();

    // =========================================================================
    // Private Member Variables
    // =========================================================================
    std::thread thread_;
    std::atomic<bool> running_{false};
    std::atomic<int> interval_ms_{16};
    StopToken stop_token_;
    EventQueue event_queue_;
};

} // namespace ap
