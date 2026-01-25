#pragma once

#include <atomic>
#include <mutex>
#include <condition_variable>
#include <chrono>

namespace ap {

/**
 * @brief Cooperative thread shutdown token.
 *
 * Provides a mechanism for requesting and checking thread shutdown,
 * as well as waiting for the stop request with optional timeout.
 */
class StopToken {
public:
    StopToken() : requested_(false) {}

    // Delete copy operations
    StopToken(const StopToken&) = delete;
    StopToken& operator=(const StopToken&) = delete;

    /**
     * @brief Request the thread to stop.
     *
     * This is a non-blocking call that signals the stop request.
     * Threads should periodically check stop_requested() and exit gracefully.
     */
    void request_stop() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            requested_ = true;
        }
        cv_.notify_all();
    }

    /**
     * @brief Check if stop has been requested.
     * @return true if stop was requested.
     */
    bool stop_requested() const {
        return requested_.load(std::memory_order_acquire);
    }

    /**
     * @brief Wait until stop is requested.
     *
     * Blocks until request_stop() is called.
     */
    void wait() {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [this] { return requested_.load(std::memory_order_acquire); });
    }

    /**
     * @brief Wait until stop is requested with timeout.
     * @param timeout Maximum time to wait.
     * @return true if stop was requested, false if timeout.
     */
    template <typename Rep, typename Period>
    bool wait_for(const std::chrono::duration<Rep, Period>& timeout) {
        std::unique_lock<std::mutex> lock(mutex_);
        return cv_.wait_for(lock, timeout, [this] {
            return requested_.load(std::memory_order_acquire);
        });
    }

    /**
     * @brief Sleep for a duration, waking early if stop is requested.
     * @param duration Time to sleep.
     * @return true if woke early due to stop request, false if slept full duration.
     */
    template <typename Rep, typename Period>
    bool sleep_for(const std::chrono::duration<Rep, Period>& duration) {
        std::unique_lock<std::mutex> lock(mutex_);
        return cv_.wait_for(lock, duration, [this] {
            return requested_.load(std::memory_order_acquire);
        });
    }

    /**
     * @brief Reset the stop token for reuse.
     */
    void reset() {
        std::lock_guard<std::mutex> lock(mutex_);
        requested_ = false;
    }

    /**
     * @brief Convenient boolean conversion.
     * @return true if stop was requested.
     */
    explicit operator bool() const {
        return stop_requested();
    }

private:
    std::atomic<bool> requested_;
    mutable std::mutex mutex_;
    std::condition_variable cv_;
};

/**
 * @brief RAII guard that requests stop on destruction.
 *
 * Useful for ensuring stop is requested when exiting a scope,
 * especially in error cases.
 */
class StopGuard {
public:
    explicit StopGuard(StopToken& token) : token_(token), active_(true) {}

    ~StopGuard() {
        if (active_) {
            token_.request_stop();
        }
    }

    // Delete copy operations
    StopGuard(const StopGuard&) = delete;
    StopGuard& operator=(const StopGuard&) = delete;

    /**
     * @brief Disable the guard so it won't request stop on destruction.
     */
    void release() {
        active_ = false;
    }

private:
    StopToken& token_;
    bool active_;
};

} // namespace ap
