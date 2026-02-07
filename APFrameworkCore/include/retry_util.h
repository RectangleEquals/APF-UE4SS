#pragma once

#include "ap_retry_types.h"
#include "stop_token.h"

#include <chrono>
#include <functional>
#include <thread>

namespace ap
{

/**
 * @brief Execute a function with retry and exponential backoff.
 *
 * @tparam Func Function type (should return bool for success/failure).
 * @param func Function to execute.
 * @param policy Retry policy configuration.
 * @param stop_token Optional stop token for early termination.
 * @return RetryResult with success status and attempt count.
 */
inline RetryResult<void> retry_with_backoff(
    std::function<bool()> func,
    const RetryPolicy& policy,
    StopToken* stop_token = nullptr
) {
    int delay_ms = policy.initial_delay_ms;

    for (int attempt = 1; attempt <= policy.max_retries + 1; ++attempt) {
        // Check for stop request
        if (stop_token && stop_token->stop_requested()) {
            return RetryResult<void>::fail("Stop requested", attempt);
        }

        try {
            if (func()) {
                return RetryResult<void>::ok(attempt);
            }
        } catch (const std::exception& e) {
            // Log error but continue retrying
            if (attempt > policy.max_retries) {
                return RetryResult<void>::fail(e.what(), attempt);
            }
        }

        // Don't sleep after last attempt
        if (attempt <= policy.max_retries) {
            if (stop_token) {
                if (stop_token->sleep_for(std::chrono::milliseconds(delay_ms))) {
                    return RetryResult<void>::fail("Stop requested during backoff", attempt);
                }
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
            }

            // Calculate next delay with backoff
            delay_ms = static_cast<int>(delay_ms * policy.backoff_multiplier);
            if (delay_ms > policy.max_delay_ms) {
                delay_ms = policy.max_delay_ms;
            }
        }
    }

    return RetryResult<void>::fail("Max retries exceeded", policy.max_retries + 1);
}

/**
 * @brief Execute a function with retry and exponential backoff, returning a value.
 *
 * @tparam T Return type.
 * @tparam Func Function type (should return std::optional<T>).
 * @param func Function to execute.
 * @param policy Retry policy configuration.
 * @param stop_token Optional stop token for early termination.
 * @return RetryResult with value if successful.
 */
template <typename T>
RetryResult<T> retry_with_backoff_value(
    std::function<std::optional<T>()> func,
    const RetryPolicy& policy,
    StopToken* stop_token = nullptr
) {
    int delay_ms = policy.initial_delay_ms;
    std::string last_error;

    for (int attempt = 1; attempt <= policy.max_retries + 1; ++attempt) {
        // Check for stop request
        if (stop_token && stop_token->stop_requested()) {
            return RetryResult<T>::fail("Stop requested", attempt);
        }

        try {
            auto result = func();
            if (result.has_value()) {
                return RetryResult<T>::ok(std::move(result.value()), attempt);
            }
        } catch (const std::exception& e) {
            last_error = e.what();
            if (attempt > policy.max_retries) {
                return RetryResult<T>::fail(last_error, attempt);
            }
        }

        // Don't sleep after last attempt
        if (attempt <= policy.max_retries) {
            if (stop_token) {
                if (stop_token->sleep_for(std::chrono::milliseconds(delay_ms))) {
                    return RetryResult<T>::fail("Stop requested during backoff", attempt);
                }
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
            }

            // Calculate next delay with backoff
            delay_ms = static_cast<int>(delay_ms * policy.backoff_multiplier);
            if (delay_ms > policy.max_delay_ms) {
                delay_ms = policy.max_delay_ms;
            }
        }
    }

    return RetryResult<T>::fail(
        last_error.empty() ? "Max retries exceeded" : last_error,
        policy.max_retries + 1
    );
}

/**
 * @brief Simple retry without backoff.
 *
 * @param func Function to execute.
 * @param max_attempts Maximum number of attempts.
 * @param delay_ms Delay between attempts.
 * @param stop_token Optional stop token.
 * @return true if succeeded within attempts.
 */
inline bool simple_retry(
    std::function<bool()> func,
    int max_attempts = 3,
    int delay_ms = 100,
    StopToken* stop_token = nullptr
) {
    for (int i = 0; i < max_attempts; ++i) {
        if (stop_token && stop_token->stop_requested()) {
            return false;
        }

        try {
            if (func()) {
                return true;
            }
        } catch (...) {
            // Ignore and retry
        }

        if (i < max_attempts - 1) {
            if (stop_token) {
                if (stop_token->sleep_for(std::chrono::milliseconds(delay_ms))) {
                    return false;
                }
            } else {
                std::this_thread::sleep_for(std::chrono::milliseconds(delay_ms));
            }
        }
    }
    return false;
}

} // namespace ap
