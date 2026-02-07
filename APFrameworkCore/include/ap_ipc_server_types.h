#pragma once

/**
 * @file ap_ipc_server_types.h
 * @brief Internal types for APIPCServer implementation.
 *
 * These types are used internally by the Windows named pipe server
 * implementation.
 */

#ifdef _WIN32
#include <Windows.h>
#endif

#include <string>
#include <vector>

namespace ap
{

#ifdef _WIN32

/**
 * @brief Represents a single client connection to the IPC server.
 *
 * Internal type used by APIPCServer for managing Windows named pipe
 * client connections.
 */
struct ClientConnection
{
    HANDLE pipe = INVALID_HANDLE_VALUE;
    OVERLAPPED overlapped = {};
    std::string client_id;
    std::vector<char> read_buffer;
    std::vector<char> write_buffer;
    bool reading = false;
    bool writing = false;
    bool pending_disconnect = false;

    ClientConnection() : read_buffer(65536), write_buffer(65536)
    {
        overlapped.hEvent = CreateEvent(nullptr, TRUE, FALSE, nullptr);
    }

    ~ClientConnection()
    {
        if (overlapped.hEvent != nullptr)
        {
            CloseHandle(overlapped.hEvent);
        }
        if (pipe != INVALID_HANDLE_VALUE)
        {
            DisconnectNamedPipe(pipe);
            CloseHandle(pipe);
        }
    }

    // Non-copyable
    ClientConnection(const ClientConnection &) = delete;
    ClientConnection &operator=(const ClientConnection &) = delete;

    // Movable
    ClientConnection(ClientConnection &&other) noexcept
        : pipe(other.pipe), overlapped(other.overlapped), client_id(std::move(other.client_id)),
          read_buffer(std::move(other.read_buffer)), write_buffer(std::move(other.write_buffer)),
          reading(other.reading), writing(other.writing), pending_disconnect(other.pending_disconnect)
    {
        other.pipe = INVALID_HANDLE_VALUE;
        other.overlapped.hEvent = nullptr;
    }

    ClientConnection &operator=(ClientConnection &&other) noexcept
    {
        if (this != &other)
        {
            // Clean up existing resources
            if (overlapped.hEvent != nullptr)
            {
                CloseHandle(overlapped.hEvent);
            }
            if (pipe != INVALID_HANDLE_VALUE)
            {
                DisconnectNamedPipe(pipe);
                CloseHandle(pipe);
            }

            // Move resources
            pipe = other.pipe;
            overlapped = other.overlapped;
            client_id = std::move(other.client_id);
            read_buffer = std::move(other.read_buffer);
            write_buffer = std::move(other.write_buffer);
            reading = other.reading;
            writing = other.writing;
            pending_disconnect = other.pending_disconnect;

            other.pipe = INVALID_HANDLE_VALUE;
            other.overlapped.hEvent = nullptr;
        }
        return *this;
    }
};

#endif // _WIN32

} // namespace ap