#pragma once

/**
 * @file ap_retry_types.h
 * @brief Types for retry operations with exponential backoff.
 */

#include "Types/ap_shared_config_types.h"

#include <optional>
#include <string>

namespace ap
{

/**
 * @brief Configuration for retry behavior.
 */
struct RetryPolicy
{
    int max_retries = 3;
    int initial_delay_ms = 1000;
    double backoff_multiplier = 2.0;
    int max_delay_ms = 10000;

    /**
     * @brief Create from RetryConfig.
     */
    static RetryPolicy from_config(const RetryConfig &config)
    {
        return {config.max_retries, config.initial_delay_ms, config.backoff_multiplier, config.max_delay_ms};
    }
};

/**
 * @brief Result of a retry operation.
 */
template <typename T>
struct RetryResult
{
    bool success = false;
    std::optional<T> value;
    int attempts = 0;
    std::string last_error;

    static RetryResult<T> ok(T val, int attempts)
    {
        return {true, std::move(val), attempts, ""};
    }

    static RetryResult<T> fail(const std::string &error, int attempts)
    {
        return {false, std::nullopt, attempts, error};
    }
};

/**
 * @brief Specialization for void operations.
 */
template <>
struct RetryResult<void>
{
    bool success = false;
    int attempts = 0;
    std::string last_error;

    static RetryResult<void> ok(int attempts)
    {
        return {true, attempts, ""};
    }

    static RetryResult<void> fail(const std::string &error, int attempts)
    {
        return {false, attempts, error};
    }
};

} // namespace ap