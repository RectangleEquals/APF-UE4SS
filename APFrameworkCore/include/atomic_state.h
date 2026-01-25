#pragma once

#include "ap_types.h"

#include <atomic>
#include <mutex>
#include <condition_variable>
#include <functional>

namespace ap {

/**
 * @brief Thread-safe wrapper for LifecycleState with change notification.
 *
 * Provides atomic access to lifecycle state and allows threads to wait
 * for specific state transitions.
 */
class AtomicState {
public:
    using StateCallback = std::function<void(LifecycleState old_state, LifecycleState new_state)>;

    AtomicState() : state_(LifecycleState::UNINITIALIZED) {}
    explicit AtomicState(LifecycleState initial) : state_(initial) {}

    // Delete copy operations
    AtomicState(const AtomicState&) = delete;
    AtomicState& operator=(const AtomicState&) = delete;

    /**
     * @brief Get the current state.
     * @return Current lifecycle state.
     */
    LifecycleState get() const {
        return state_.load(std::memory_order_acquire);
    }

    /**
     * @brief Set a new state.
     * @param new_state State to set.
     *
     * Notifies all waiting threads and calls the state change callback if set.
     */
    void set(LifecycleState new_state) {
        LifecycleState old_state;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            old_state = state_.exchange(new_state, std::memory_order_release);
        }
        cv_.notify_all();

        if (callback_ && old_state != new_state) {
            callback_(old_state, new_state);
        }
    }

    /**
     * @brief Atomically compare and set state.
     * @param expected Expected current state.
     * @param desired Desired new state.
     * @return true if state was changed, false if current state didn't match expected.
     */
    bool compare_and_set(LifecycleState expected, LifecycleState desired) {
        LifecycleState old_expected = expected;
        bool success;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            success = state_.compare_exchange_strong(
                expected, desired,
                std::memory_order_acq_rel,
                std::memory_order_acquire
            );
        }

        if (success) {
            cv_.notify_all();
            if (callback_) {
                callback_(old_expected, desired);
            }
        }

        return success;
    }

    /**
     * @brief Wait until state matches the specified value.
     * @param target_state State to wait for.
     */
    void wait_for(LifecycleState target_state) {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [this, target_state] {
            return state_.load(std::memory_order_acquire) == target_state;
        });
    }

    /**
     * @brief Wait until state matches any of the specified values.
     * @param states Set of acceptable states.
     * @return The state that was matched.
     */
    LifecycleState wait_for_any(std::initializer_list<LifecycleState> states) {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [this, &states] {
            auto current = state_.load(std::memory_order_acquire);
            for (auto s : states) {
                if (current == s) return true;
            }
            return false;
        });
        return state_.load(std::memory_order_acquire);
    }

    /**
     * @brief Wait until state matches with timeout.
     * @param target_state State to wait for.
     * @param timeout Maximum time to wait.
     * @return true if state matched, false if timeout.
     */
    template <typename Rep, typename Period>
    bool wait_for(LifecycleState target_state,
                  const std::chrono::duration<Rep, Period>& timeout) {
        std::unique_lock<std::mutex> lock(mutex_);
        return cv_.wait_for(lock, timeout, [this, target_state] {
            return state_.load(std::memory_order_acquire) == target_state;
        });
    }

    /**
     * @brief Set callback for state changes.
     * @param callback Function to call on state change (old_state, new_state).
     */
    void set_callback(StateCallback callback) {
        callback_ = std::move(callback);
    }

    /**
     * @brief Check if current state is an error state.
     * @return true if in ERROR_STATE.
     */
    bool is_error() const {
        return get() == LifecycleState::ERROR_STATE;
    }

    /**
     * @brief Check if current state is active.
     * @return true if in ACTIVE state.
     */
    bool is_active() const {
        return get() == LifecycleState::ACTIVE;
    }

    /**
     * @brief Operator for convenient state access.
     * @return Current state.
     */
    operator LifecycleState() const {
        return get();
    }

private:
    std::atomic<LifecycleState> state_;
    mutable std::mutex mutex_;
    std::condition_variable cv_;
    StateCallback callback_;
};

} // namespace ap
