#include "ap_multipart_message.h"
#include "ap_base64.h"

#include <zlib.h>

#include <stdexcept>

namespace ap
{

// =============================================================================
// Receiver configuration
// =============================================================================

void APMultipartMessage::set_callback(AssemblyCallback cb)
{
    on_complete_ = std::move(cb);
}

void APMultipartMessage::set_progress_callback(ProgressCallback cb)
{
    on_progress_ = std::move(cb);
}

// =============================================================================
// Sender
// =============================================================================

bool APMultipartMessage::needs_splitting(const IPCMessage &msg)
{
    return msg.to_json().dump().size() > SPLIT_THRESHOLD;
}

std::vector<IPCMessage> APMultipartMessage::prepare(const IPCMessage &msg)
{
    // Step 1: Serialize to JSON
    std::string json_str = msg.to_json().dump();

    // Step 2: Compress entire JSON with zlib
    uLong src_len = static_cast<uLong>(json_str.size());
    uLong bound   = compressBound(src_len);
    std::vector<Bytef> compressed(bound);

    if (compress2(compressed.data(), &bound,
                  reinterpret_cast<const Bytef *>(json_str.data()), src_len,
                  Z_DEFAULT_COMPRESSION) != Z_OK)
    {
        return {};
    }
    compressed.resize(bound);

    // Step 3 & 4: Split into CHUNK_BYTES slices and base64-encode each
    size_t total_compressed = compressed.size();
    int    num_chunks       = static_cast<int>((total_compressed + CHUNK_BYTES - 1) / CHUNK_BYTES);
    if (num_chunks == 0)
    {
        return {};
    }

    std::string msg_id = std::to_string(++next_id_);

    std::vector<IPCMessage> chunks;
    chunks.reserve(num_chunks);

    for (int i = 0; i < num_chunks; ++i)
    {
        size_t offset    = static_cast<size_t>(i) * CHUNK_BYTES;
        size_t slice_len = std::min(CHUNK_BYTES, total_compressed - offset);

        // Binary-safe: construct std::string from raw bytes for base64_encode
        std::string slice(reinterpret_cast<const char *>(compressed.data() + offset), slice_len);
        std::string encoded = base64_encode(slice);

        IPCMessage chunk;
        chunk.type   = IPCMessageType::MULTIPART_CHUNK;
        chunk.source = msg.source;
        chunk.target = msg.target;
        chunk.payload = {
            {"msg_id",    msg_id},
            {"part",      i + 1},
            {"total",     num_chunks},
            {"orig_size", static_cast<uint64_t>(json_str.size())},
            {"orig_type", msg.type},
            {"data",      std::move(encoded)}
        };
        chunks.push_back(std::move(chunk));
    }

    return chunks;
}

// =============================================================================
// Receiver
// =============================================================================

void APMultipartMessage::receive(const IPCMessage &chunk_msg)
{
    if (chunk_msg.type != IPCMessageType::MULTIPART_CHUNK)
    {
        return;
    }

    const auto &p       = chunk_msg.payload;
    std::string msg_id   = p.value("msg_id", "");
    int         part     = p.value("part", 0);
    int         total    = p.value("total", 0);
    uint64_t    orig_size = p.value("orig_size", uint64_t(0));
    std::string orig_type = p.value("orig_type", "");
    std::string data     = p.value("data", "");

    if (msg_id.empty() || part <= 0 || total <= 0)
    {
        return;
    }

    Assembly &assembly     = in_progress_[msg_id];
    assembly.total_parts   = total;
    assembly.orig_size     = orig_size;
    assembly.orig_type     = orig_type;
    assembly.parts[part]   = std::move(data);

    // Fire progress callback (approximate: sum of base64-encoded chunk sizes)
    if (on_progress_)
    {
        size_t bytes_acc = 0;
        for (const auto &[_, part_data] : assembly.parts)
        {
            bytes_acc += part_data.size();
        }
        on_progress_(part, total, bytes_acc, orig_type);
    }

    if (assembly.is_complete())
    {
        // Concatenate base64-decoded slices in order → compressed byte stream
        std::string compressed;
        for (int i = 1; i <= total; ++i)
        {
            compressed += base64_decode(assembly.parts[i]);
        }

        // Decompress with zlib
        uLong out_len = static_cast<uLong>(orig_size);
        std::vector<Bytef> output(out_len);

        if (uncompress(output.data(), &out_len,
                       reinterpret_cast<const Bytef *>(compressed.data()),
                       static_cast<uLong>(compressed.size())) == Z_OK)
        {
            std::string json_str(reinterpret_cast<const char *>(output.data()), out_len);
            if (on_complete_)
            {
                on_complete_(std::move(json_str));
            }
        }

        in_progress_.erase(msg_id);
    }
}

} // namespace ap
