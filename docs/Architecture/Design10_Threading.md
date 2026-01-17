# Design10: Threading and Synchronization

> Thread safety, synchronization primitives, and race condition prevention.

---

## Overview

The framework operates across multiple threads that must be carefully synchronized to prevent race conditions and ensure data consistency.

---

## Thread Model

### Threads in APFrameworkCore

| Thread | Owner | Purpose |
|--------|-------|---------|
| **Main Thread** | UE4SS | Runs Lua mods, calls `APManager::update()` |
| **Polling Thread** | APPollingThread | Continuously polls AP server for messages |
| **IPC Thread** | APIPCServer | Handles named pipe connections and message I/O |

### Thread Responsibilities

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              THREAD MODEL                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ MAIN THREAD (UE4SS External Thread)                                  │   │
│  │                                                                       │   │
│  │  • Executes mod top-level code                                       │   │
│  │  • Calls APManager::update() each tick                               │   │
│  │  • Processes queued callbacks (item actions, lifecycle notifications)│   │
│  │  • State transitions (ONLY thread that can change lifecycle state)   │   │
│  │  • Lua function execution via APActionExecutor                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           │ mutex-protected queues                                          │
│           ▼                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ POLLING THREAD (APPollingThread)                                     │   │
│  │                                                                       │   │
│  │  • Polls AP server via apclientpp                                    │   │
│  │  • Enqueues received messages to thread-safe queue                   │   │
│  │  • NEVER directly executes actions or changes state                  │   │
│  │  • Runs at configurable interval (default 16ms)                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│           │                                                                  │
│           │ mutex-protected queues                                          │
│           ▼                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ IPC THREAD (APIPCServer)                                             │   │
│  │                                                                       │   │
│  │  • Accepts named pipe connections                                    │   │
│  │  • Reads/writes IPC messages asynchronously                          │   │
│  │  • Enqueues received messages to thread-safe queue                   │   │
│  │  • Dequeues outgoing messages from thread-safe queue                 │   │
│  │  • NEVER directly processes messages or changes state                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Critical Invariant

**Only the Main Thread may:**
- Change the lifecycle state (`current_state_`)
- Execute Lua functions (action execution)
- Modify capability tables
- Update session state (received item index, checked locations)

**Background threads (Polling, IPC) may only:**
- Enqueue messages to thread-safe queues
- Dequeue messages from thread-safe queues
- Read (not write) current lifecycle state for logging

This design ensures all state mutations happen on a single thread, eliminating most race conditions.

---

## Synchronization Primitives

### Message Queues

All inter-thread communication uses mutex-protected queues:

```cpp
template<typename T>
class ThreadSafeQueue {
public:
    void push(T item) {
        std::lock_guard<std::mutex> lock(mutex_);
        queue_.push(std::move(item));
        cv_.notify_one();
    }

    std::optional<T> try_pop() {
        std::lock_guard<std::mutex> lock(mutex_);
        if (queue_.empty()) return std::nullopt;
        T item = std::move(queue_.front());
        queue_.pop();
        return item;
    }

    std::vector<T> pop_all() {
        std::lock_guard<std::mutex> lock(mutex_);
        std::vector<T> items;
        while (!queue_.empty()) {
            items.push_back(std::move(queue_.front()));
            queue_.pop();
        }
        return items;
    }

    size_t size() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return queue_.size();
    }

private:
    mutable std::mutex mutex_;
    std::condition_variable cv_;
    std::queue<T> queue_;
};
```

### Queue Instances

| Queue | Producer | Consumer | Content |
|-------|----------|----------|---------|
| `ap_message_queue_` | Polling Thread | Main Thread | Messages from AP server |
| `ipc_incoming_queue_` | IPC Thread | Main Thread | Messages from client mods |
| `ipc_outgoing_queue_` | Main Thread | IPC Thread | Messages to client mods |
| `action_result_queue_` | IPC Thread | Main Thread | Action execution results |

---

## State Access Patterns

### Lifecycle State

```cpp
class APManager {
private:
    std::atomic<LifecycleState> current_state_;  // Atomic for safe reads
    std::mutex state_transition_mutex_;           // Mutex for transitions

public:
    // Safe read from any thread
    LifecycleState get_state() const {
        return current_state_.load(std::memory_order_acquire);
    }

    // Only called from Main Thread
    void transition_to(LifecycleState new_state) {
        std::lock_guard<std::mutex> lock(state_transition_mutex_);

        // Validate transition is allowed
        if (!is_valid_transition(current_state_.load(), new_state)) {
            throw InvalidStateTransition(...);
        }

        // Perform transition actions
        on_exit_state(current_state_.load());
        current_state_.store(new_state, std::memory_order_release);
        on_enter_state(new_state);
    }
};
```

### Session State

Session state (received item index, checked locations) is only modified by Main Thread:

```cpp
class APStateManager {
private:
    std::mutex mutex_;  // Protects all state
    int received_item_index_;
    std::set<int64_t> checked_locations_;

public:
    // Called from Main Thread only
    void set_received_item_index(int index) {
        std::lock_guard<std::mutex> lock(mutex_);
        received_item_index_ = index;
        save_state_async();  // Non-blocking save
    }

    // Can be called from any thread (for logging/display)
    int get_received_item_index() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return received_item_index_;
    }
};
```

---

## Message Processing Flow

### Main Thread Update Cycle

```cpp
void APManager::update() {
    // 1. Process all AP server messages
    auto ap_messages = ap_message_queue_.pop_all();
    for (const auto& msg : ap_messages) {
        process_ap_message(msg);  // May enqueue IPC messages
    }

    // 2. Process all IPC incoming messages
    auto ipc_messages = ipc_incoming_queue_.pop_all();
    for (const auto& msg : ipc_messages) {
        process_ipc_message(msg);  // May change state, enqueue responses
    }

    // 3. Process action results
    auto results = action_result_queue_.pop_all();
    for (const auto& result : results) {
        process_action_result(result);
    }

    // 4. Check for timeouts
    check_registration_timeout();
    check_action_timeouts();

    // 5. State-specific processing
    switch (get_state()) {
        case LifecycleState::ACTIVE:
            // Normal operation
            break;
        case LifecycleState::ERROR_STATE:
            // Only process recovery commands
            break;
        // ... other states
    }
}
```

### Polling Thread Loop

```cpp
void APPollingThread::run() {
    while (!should_stop_.load()) {
        // Poll AP server (blocking with timeout)
        ap_client_->poll();

        // Get any received messages
        auto messages = ap_client_->get_messages();

        // Enqueue for Main Thread processing
        for (auto& msg : messages) {
            ap_message_queue_.push(std::move(msg));
        }

        // Sleep for polling interval
        std::this_thread::sleep_for(polling_interval_);
    }
}
```

### IPC Thread Loop

```cpp
void APIPCServer::run() {
    while (!should_stop_.load()) {
        // Accept new connections (non-blocking)
        accept_pending_connections();

        // Read from all connected clients
        for (auto& client : connected_clients_) {
            auto messages = client.read_available();
            for (auto& msg : messages) {
                ipc_incoming_queue_.push(std::move(msg));
            }
        }

        // Send queued outgoing messages
        auto outgoing = ipc_outgoing_queue_.pop_all();
        for (const auto& msg : outgoing) {
            send_to_target(msg);
        }

        std::this_thread::sleep_for(ipc_poll_interval_);
    }
}
```

---

## Race Condition Prevention

### State Transition During Message Processing

**Scenario:** CMD_RESYNC arrives while processing item receipt

**Prevention:**
1. Main Thread processes messages sequentially in `update()`
2. State transitions happen between message batches, not during
3. After transition, remaining messages in queue are processed according to new state

```cpp
void APManager::process_ipc_message(const IPCMessage& msg) {
    // Check if message is valid for current state
    if (!is_message_valid_for_state(msg, get_state())) {
        send_rejection(msg.source, "Invalid in current state");
        return;
    }

    // Process message
    if (msg.type == "cmd_resync") {
        // Mark that resync is pending
        pending_resync_ = true;
        // Don't transition immediately - finish current batch
    }
    // ... other message handling
}

void APManager::update() {
    // Process all messages first
    process_all_messages();

    // Then handle pending transitions
    if (pending_resync_ && get_state() == LifecycleState::ACTIVE) {
        transition_to(LifecycleState::RESYNCING);
        pending_resync_ = false;
    }
}
```

### Action Execution Timeout

**Scenario:** Mod receives `execute_action` but never sends `action_result`

**Prevention:**
1. Main Thread tracks pending actions with timestamps
2. Each `update()` checks for timed-out actions
3. Timeout triggers ERROR_STATE

```cpp
struct PendingAction {
    int64_t item_id;
    std::string mod_id;
    std::chrono::steady_clock::time_point sent_at;
};

class APManager {
private:
    std::vector<PendingAction> pending_actions_;
    std::chrono::milliseconds action_timeout_{5000};  // 5 second default

public:
    void send_execute_action(const std::string& mod_id, int64_t item_id, ...) {
        // Send IPC message
        ipc_outgoing_queue_.push(create_execute_action_message(...));

        // Track pending action
        pending_actions_.push_back({
            item_id,
            mod_id,
            std::chrono::steady_clock::now()
        });
    }

    void check_action_timeouts() {
        auto now = std::chrono::steady_clock::now();

        for (auto it = pending_actions_.begin(); it != pending_actions_.end();) {
            if (now - it->sent_at > action_timeout_) {
                // Action timed out - enter ERROR_STATE
                log_error("Action timeout for item " + std::to_string(it->item_id) +
                         " from mod " + it->mod_id);
                transition_to(LifecycleState::ERROR_STATE);
                return;  // Stop processing, we're in error state
            }
            ++it;
        }
    }

    void process_action_result(const ActionResult& result) {
        // Remove from pending
        auto it = std::find_if(pending_actions_.begin(), pending_actions_.end(),
            [&](const PendingAction& p) { return p.item_id == result.item_id; });

        if (it != pending_actions_.end()) {
            pending_actions_.erase(it);
        }

        if (!result.success) {
            // Action failed - enter ERROR_STATE
            log_error("Action failed for item " + std::to_string(result.item_id) +
                     ": " + result.error);
            transition_to(LifecycleState::ERROR_STATE);
        }
    }
};
```

### Shutdown Coordination

**Scenario:** Framework shutting down while threads are active

**Prevention:**
1. Set atomic stop flag
2. Wait for threads to drain queues
3. Join threads before destroying shared resources

```cpp
void APManager::shutdown() {
    // 1. Signal all threads to stop
    should_stop_.store(true);

    // 2. Wake up any waiting threads
    ap_message_queue_.notify_all();
    ipc_incoming_queue_.notify_all();

    // 3. Wait for threads to finish
    if (polling_thread_.joinable()) {
        polling_thread_.join();
    }
    if (ipc_thread_.joinable()) {
        ipc_thread_.join();
    }

    // 4. Process any remaining messages (optional cleanup)
    drain_remaining_messages();

    // 5. Save final state
    state_manager_->save_state_sync();
}
```

---

## Thread Safety Guarantees

### What is Thread-Safe

| Component | Thread-Safe | Notes |
|-----------|-------------|-------|
| Message queues | Yes | Mutex-protected |
| Lifecycle state read | Yes | Atomic load |
| Lifecycle state write | No | Main Thread only |
| Session state read | Yes | Mutex-protected |
| Session state write | No | Main Thread only |
| Logging | Yes | Internal mutex |
| Config read | Yes | Immutable after init |
| Config write | No | Main Thread only |

### What is NOT Thread-Safe

| Component | Why | Mitigation |
|-----------|-----|------------|
| Capability tables | Modified during GENERATION | Only accessed in specific states |
| Mod registry | Modified during DISCOVERY/REGISTRATION | Only accessed in specific states |
| Lua state access | sol2 is not thread-safe | Only Main Thread executes Lua |
| AP client internal state | apclientpp not thread-safe | Only Polling Thread uses it |

---

## APClientLib Threading

APClientLib runs entirely on the Main Thread within the client mod's context:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLIENT MOD THREADING                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ MAIN THREAD (same as UE4SS External Thread)                          │   │
│  │                                                                       │   │
│  │  Client Mod                    APClientLib                           │   │
│  │  ┌─────────────┐              ┌─────────────────────┐                │   │
│  │  │ main.lua    │──register───►│ APIPCClient         │                │   │
│  │  │             │              │ (sync pipe I/O)     │                │   │
│  │  │ on_lifecycle│◄──callback───│                     │                │   │
│  │  │ on_item     │◄──callback───│ APActionExecutor    │                │   │
│  │  │             │              │ (executes Lua funcs)│                │   │
│  │  └─────────────┘              └─────────────────────┘                │   │
│  │                                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  Note: APClientLib does NOT spawn threads.                                  │
│  All pipe I/O is synchronous with timeouts.                                 │
│  Callbacks are invoked on the Main Thread.                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why No Threads in APClientLib?

1. **Simplicity** — Client mods don't need to handle threading
2. **Lua safety** — sol2/Lua state isn't thread-safe
3. **Determinism** — Actions execute in predictable order
4. **UE4SS compatibility** — Follows UE4SS's single-thread-for-Lua model

### Blocking Considerations

APClientLib pipe operations use timeouts to prevent blocking:

```cpp
class APIPCClient {
public:
    bool send_message(const IPCMessage& msg, int timeout_ms = 1000) {
        // Non-blocking write with timeout
        return pipe_.write(serialize(msg), timeout_ms);
    }

    std::optional<IPCMessage> receive_message(int timeout_ms = 0) {
        // Non-blocking read (returns immediately if no data)
        auto data = pipe_.read(timeout_ms);
        if (data.empty()) return std::nullopt;
        return deserialize(data);
    }
};
```

---

## Configuration

Threading-related configuration in `framework_config.json`:

```json
{
  "threading": {
    "polling_interval_ms": 16,
    "ipc_poll_interval_ms": 10,
    "action_timeout_ms": 5000,
    "queue_max_size": 1000,
    "shutdown_timeout_ms": 5000
  }
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `polling_interval_ms` | 16 | AP server poll interval (~60fps) |
| `ipc_poll_interval_ms` | 10 | IPC I/O poll interval |
| `action_timeout_ms` | 5000 | Time to wait for action_result before ERROR_STATE |
| `queue_max_size` | 1000 | Max messages per queue before overflow |
| `shutdown_timeout_ms` | 5000 | Max time to wait for threads during shutdown |

---

## Debugging Thread Issues

### Logging Thread Context

All log entries include thread identification:

```
[2024-01-15T12:30:45.123] [INFO] [Main] [APManager] Processing item receipt
[2024-01-15T12:30:45.124] [DEBUG] [Poll] [APPollingThread] Received 3 messages
[2024-01-15T12:30:45.125] [DEBUG] [IPC] [APIPCServer] Client connected: mymod.game.mod
```

### Deadlock Detection

The framework includes optional deadlock detection in debug builds:

```cpp
#ifdef AP_DEBUG
class DeadlockDetector {
public:
    void on_lock_acquire(const char* mutex_name, const char* file, int line);
    void on_lock_release(const char* mutex_name);
    void check_for_cycles();  // Called periodically
};
#endif
```

### Thread Sanitizer Compatibility

The codebase is designed to be compatible with ThreadSanitizer (TSan):

```cmake
if(CMAKE_BUILD_TYPE STREQUAL "Debug" AND ENABLE_TSAN)
    target_compile_options(APFrameworkCore PRIVATE -fsanitize=thread)
    target_link_options(APFrameworkCore PRIVATE -fsanitize=thread)
endif()
```