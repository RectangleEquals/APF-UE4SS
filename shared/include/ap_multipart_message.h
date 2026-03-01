#pragma once

/**
 * @file ap_multipart_message.h
 * @brief Transparent compression + chunked splitting/reassembly for large IPC messages.
 */

#include "Types/ap_shared_ipc_types.h"

#include <functional>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>

namespace ap
{

/**
 * @brief Handles zlib compression and chunked splitting/reassembly of large IPC messages.
 *
 * When an IPCMessage's serialized JSON exceeds SPLIT_THRESHOLD bytes, compress it
 * with zlib and split the compressed bytes into CHUNK_BYTES-sized slices. Each slice
 * is base64-encoded and sent as a separate MULTIPART_CHUNK IPCMessage.
 *
 * The receiver accumulates chunks by msg_id, decompresses when all parts arrive,
 * and fires AssemblyCallback with the original JSON string.
 *
 * One instance per connection (per ClientConnection on the server; per APIPCClient
 * on the client). next_id_ is a per-instance counter so all APMultipartMessage
 * instances sharing the same process/DLL remain independent.
 *
 * Base64 encoding is required because the IPC wire format is JSON: raw binary bytes
 * (including null bytes) cannot be embedded in a JSON string field.
 */
class APMultipartMessage
{
  public:
    /**
     * @brief Fired with the fully decompressed JSON string when all chunks are assembled.
     */
    using AssemblyCallback = std::function<void(std::string assembled_json)>;

    /**
     * @brief Fired after each chunk is received (for progress logging / diagnostics).
     * @param part      1-based index of the chunk just received.
     * @param total     Total number of chunks in this message.
     * @param bytes_acc Approximate total compressed bytes received so far.
     * @param orig_type Original message type (e.g. "tracker_snapshot") — diagnostic only.
     *
     * Note: orig_type is purely informational. Splitting is size-based only — every
     * message whose serialized JSON exceeds SPLIT_THRESHOLD is split, regardless of type.
     */
    using ProgressCallback = std::function<void(
        int part, int total, size_t bytes_acc, const std::string &orig_type)>;

    // -------------------------------------------------------------------------
    // Chunk-size constants
    //
    // Each chunk frame sent over the pipe = [4-byte prefix] + [JSON string].
    // The JSON string contains all envelope fields plus the base64-encoded data.
    //
    // Available for base64 payload per chunk:
    //   PIPE_BUFFER_SIZE - 4 (prefix) - METADATA_RESERVE = 64508 bytes
    //
    // Max raw compressed bytes such that base64(bytes) fits in 64508:
    //   floor(64508 * 3/4) = 48381 bytes
    //
    // CHUNK_BYTES = 32 * 1024 = 32768  (conservative; leaves ~21 KB of margin)
    // Verification: ceil(32768/3)*4 = 43692 bytes base64
    //               43692 + 1024 + 4 = 44720 < 65536 ✓
    // -------------------------------------------------------------------------
    static constexpr size_t PIPE_BUFFER_SIZE = 65536; ///< Named pipe buffer (both sides)
    static constexpr size_t METADATA_RESERVE = 1024;  ///< JSON envelope overhead (conservative)
    static constexpr size_t CHUNK_BYTES      = 32 * 1024; ///< Raw compressed bytes per chunk
    static constexpr size_t SPLIT_THRESHOLD  = 48 * 1024; ///< Split if serialized JSON > this

    // Compile-time safety: base64(CHUNK_BYTES) + metadata overhead + prefix <= PIPE_BUFFER_SIZE
    static_assert(((CHUNK_BYTES + 2) / 3) * 4 + METADATA_RESERVE + 4 <= PIPE_BUFFER_SIZE,
                  "CHUNK_BYTES too large — chunk frame would exceed PIPE_BUFFER_SIZE");

    APMultipartMessage()  = default;
    ~APMultipartMessage() = default;

    // Non-copyable; movable (supports ClientConnection move semantics)
    APMultipartMessage(const APMultipartMessage &)            = delete;
    APMultipartMessage &operator=(const APMultipartMessage &) = delete;
    APMultipartMessage(APMultipartMessage &&)                 = default;
    APMultipartMessage &operator=(APMultipartMessage &&)      = default;

    // -------------------------------------------------------------------------
    // Receiver configuration
    // -------------------------------------------------------------------------

    /**
     * @brief Set the callback invoked when a message is fully assembled and decompressed.
     */
    void set_callback(AssemblyCallback cb);

    /**
     * @brief Set optional per-chunk progress callback.
     */
    void set_progress_callback(ProgressCallback cb);

    // -------------------------------------------------------------------------
    // Sender
    // -------------------------------------------------------------------------

    /**
     * @brief Return true if the message's serialized JSON exceeds SPLIT_THRESHOLD.
     *
     * Purely size-based — every oversized message is split regardless of type.
     */
    static bool needs_splitting(const IPCMessage &msg);

    /**
     * @brief Compress and split a message into MULTIPART_CHUNK IPCMessages.
     *
     * Workflow:
     *   1. Serialize to JSON string.
     *   2. zlib compress2() the entire JSON.
     *   3. Split compressed bytes into CHUNK_BYTES-sized slices.
     *   4. base64_encode() each slice → "data" field.
     *   5. Emit one MULTIPART_CHUNK IPCMessage per slice (source/target preserved).
     *
     * Uses per-instance next_id_ as a monotonically increasing message identifier.
     *
     * @return Vector of chunk messages ready to send, or empty vector on failure.
     */
    std::vector<IPCMessage> prepare(const IPCMessage &msg);

    // -------------------------------------------------------------------------
    // Receiver
    // -------------------------------------------------------------------------

    /**
     * @brief Feed one MULTIPART_CHUNK message.
     *
     * Stores the chunk in the in-progress assembly for the given msg_id.
     * Fires progress_callback after each chunk. When all parts are present,
     * concatenates decoded slices, decompresses with zlib uncompress(), and
     * fires assembly_callback with the original JSON string.
     *
     * @param chunk_msg A MULTIPART_CHUNK IPCMessage (other types are silently ignored).
     */
    void receive(const IPCMessage &chunk_msg);

  private:
    struct Assembly
    {
        int total_parts   = 0;
        uint64_t orig_size = 0;
        std::string orig_type;
        std::map<int, std::string> parts; // 1-based part index → base64-encoded compressed slice

        bool is_complete() const
        {
            return total_parts > 0 && static_cast<int>(parts.size()) == total_parts;
        }
    };

    AssemblyCallback  on_complete_;
    ProgressCallback  on_progress_;
    std::unordered_map<std::string, Assembly> in_progress_;
    uint64_t next_id_ = 0; ///< Per-instance counter; incremented by prepare()
};

} // namespace ap
