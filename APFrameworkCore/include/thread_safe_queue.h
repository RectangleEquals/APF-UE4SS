#pragma once

#include <queue>
#include <mutex>
#include <condition_variable>
#include <optional>
#include <chrono>

namespace ap {

/**
 * @brief Thread-safe queue implementation using mutex and condition variable.
 *
 * Provides blocking and non-blocking operations for producer-consumer patterns.
 *
 * @tparam T Type of elements stored in the queue.
 */
template <typename T>
class ThreadSafeQueue {
public:
    /**
     * @brief Construct a queue with optional maximum size.
     * @param max_size Maximum number of elements (0 = unlimited).
     */
    explicit ThreadSafeQueue(size_t max_size = 0)
        : max_size_(max_size), shutdown_(false) {}

    // Delete copy operations
    ThreadSafeQueue(const ThreadSafeQueue&) = delete;
    ThreadSafeQueue& operator=(const ThreadSafeQueue&) = delete;

    // Allow move operations
    ThreadSafeQueue(ThreadSafeQueue&& other) noexcept {
        std::lock_guard<std::mutex> lock(other.mutex_);
        queue_ = std::move(other.queue_);
        max_size_ = other.max_size_;
        shutdown_ = other.shutdown_.load();
    }

    ThreadSafeQueue& operator=(ThreadSafeQueue&& other) noexcept {
        if (this != &other) {
            std::scoped_lock lock(mutex_, other.mutex_);
            queue_ = std::move(other.queue_);
            max_size_ = other.max_size_;
            shutdown_ = other.shutdown_.load();
        }
        return *this;
    }

    /**
     * @brief Push an element to the queue.
     * @param item Item to push.
     * @return true if pushed, false if queue is at max capacity or shutdown.
     */
    bool push(const T& item) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (shutdown_) {
                return false;
            }
            if (max_size_ > 0 && queue_.size() >= max_size_) {
                return false;
            }
            queue_.push(item);
        }
        cv_.notify_one();
        return true;
    }

    /**
     * @brief Push an element to the queue (move version).
     * @param item Item to push.
     * @return true if pushed, false if queue is at max capacity or shutdown.
     */
    bool push(T&& item) {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (shutdown_) {
                return false;
            }
            if (max_size_ > 0 && queue_.size() >= max_size_) {
                return false;
            }
            queue_.push(std::move(item));
        }
        cv_.notify_one();
        return true;
    }

    /**
     * @brief Try to pop an element without blocking.
     * @return The element if available, std::nullopt otherwise.
     */
    std::optional<T> try_pop() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (queue_.empty()) {
            return std::nullopt;
        }
        T item = std::move(queue_.front());
        queue_.pop();
        return item;
    }

    /**
     * @brief Pop an element, blocking until one is available.
     * @return The element, or std::nullopt if queue was shut down.
     */
    std::optional<T> pop() {
        std::unique_lock<std::mutex> lock(mutex_);
        cv_.wait(lock, [this] { return !queue_.empty() || shutdown_; });

        if (shutdown_ && queue_.empty()) {
            return std::nullopt;
        }

        T item = std::move(queue_.front());
        queue_.pop();
        return item;
    }

    /**
     * @brief Pop an element with timeout.
     * @param timeout Maximum time to wait.
     * @return The element if available within timeout, std::nullopt otherwise.
     */
    template <typename Rep, typename Period>
    std::optional<T> pop_for(const std::chrono::duration<Rep, Period>& timeout) {
        std::unique_lock<std::mutex> lock(mutex_);
        if (!cv_.wait_for(lock, timeout, [this] { return !queue_.empty() || shutdown_; })) {
            return std::nullopt;  // Timeout
        }

        if (shutdown_ && queue_.empty()) {
            return std::nullopt;
        }

        T item = std::move(queue_.front());
        queue_.pop();
        return item;
    }

    /**
     * @brief Pop all available elements without blocking.
     * @return Vector of all elements that were in the queue.
     */
    std::vector<T> pop_all() {
        std::vector<T> items;
        std::lock_guard<std::mutex> lock(mutex_);
        items.reserve(queue_.size());
        while (!queue_.empty()) {
            items.push_back(std::move(queue_.front()));
            queue_.pop();
        }
        return items;
    }

    /**
     * @brief Check if the queue is empty.
     * @return true if empty.
     */
    bool empty() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return queue_.empty();
    }

    /**
     * @brief Get the current size of the queue.
     * @return Number of elements in the queue.
     */
    size_t size() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return queue_.size();
    }

    /**
     * @brief Clear all elements from the queue.
     */
    void clear() {
        std::lock_guard<std::mutex> lock(mutex_);
        std::queue<T> empty;
        std::swap(queue_, empty);
    }

    /**
     * @brief Signal shutdown to all waiting threads.
     *
     * After shutdown, pop operations will return std::nullopt when queue is empty,
     * and push operations will fail.
     */
    void shutdown() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            shutdown_ = true;
        }
        cv_.notify_all();
    }

    /**
     * @brief Check if the queue has been shut down.
     * @return true if shutdown was called.
     */
    bool is_shutdown() const {
        return shutdown_;
    }

    /**
     * @brief Reset the queue for reuse after shutdown.
     */
    void reset() {
        std::lock_guard<std::mutex> lock(mutex_);
        shutdown_ = false;
        std::queue<T> empty;
        std::swap(queue_, empty);
    }

private:
    mutable std::mutex mutex_;
    std::condition_variable cv_;
    std::queue<T> queue_;
    size_t max_size_;
    std::atomic<bool> shutdown_;
};

} // namespace ap
