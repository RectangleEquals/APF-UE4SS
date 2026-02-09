#include "ap_base64.h"

#include <array>
#include <cstdint>
#include <stdexcept>

namespace ap
{

static constexpr char ENCODE_TABLE[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static constexpr std::array<uint8_t, 256> make_decode_table()
{
    std::array<uint8_t, 256> table{};
    for (auto &v : table)
    {
        v = 0xFF; // invalid
    }
    for (int i = 0; i < 64; ++i)
    {
        table[static_cast<uint8_t>(ENCODE_TABLE[i])] = static_cast<uint8_t>(i);
    }
    table[static_cast<uint8_t>('=')] = 0; // padding
    return table;
}

static constexpr auto DECODE_TABLE = make_decode_table();

std::string base64_encode(const std::string &input)
{
    std::string output;
    output.reserve(((input.size() + 2) / 3) * 4);

    size_t i = 0;
    const auto *data = reinterpret_cast<const uint8_t *>(input.data());
    size_t len = input.size();

    for (; i + 2 < len; i += 3)
    {
        uint32_t triple = (static_cast<uint32_t>(data[i]) << 16) |
                          (static_cast<uint32_t>(data[i + 1]) << 8) |
                          static_cast<uint32_t>(data[i + 2]);

        output += ENCODE_TABLE[(triple >> 18) & 0x3F];
        output += ENCODE_TABLE[(triple >> 12) & 0x3F];
        output += ENCODE_TABLE[(triple >> 6) & 0x3F];
        output += ENCODE_TABLE[triple & 0x3F];
    }

    if (i < len)
    {
        uint32_t triple = static_cast<uint32_t>(data[i]) << 16;
        if (i + 1 < len)
        {
            triple |= static_cast<uint32_t>(data[i + 1]) << 8;
        }

        output += ENCODE_TABLE[(triple >> 18) & 0x3F];
        output += ENCODE_TABLE[(triple >> 12) & 0x3F];

        if (i + 1 < len)
        {
            output += ENCODE_TABLE[(triple >> 6) & 0x3F];
        }
        else
        {
            output += '=';
        }
        output += '=';
    }

    return output;
}

std::string base64_decode(const std::string &input)
{
    if (input.empty())
    {
        return "";
    }

    // Strip whitespace and count valid characters
    std::string clean;
    clean.reserve(input.size());
    for (char c : input)
    {
        if (c != '\n' && c != '\r' && c != ' ' && c != '\t')
        {
            clean += c;
        }
    }

    if (clean.size() % 4 != 0)
    {
        throw std::invalid_argument("Invalid base64 input length");
    }

    size_t padding = 0;
    if (!clean.empty() && clean[clean.size() - 1] == '=')
    {
        ++padding;
    }
    if (clean.size() > 1 && clean[clean.size() - 2] == '=')
    {
        ++padding;
    }

    std::string output;
    output.reserve((clean.size() / 4) * 3 - padding);

    for (size_t i = 0; i < clean.size(); i += 4)
    {
        uint8_t a = DECODE_TABLE[static_cast<uint8_t>(clean[i])];
        uint8_t b = DECODE_TABLE[static_cast<uint8_t>(clean[i + 1])];
        uint8_t c = DECODE_TABLE[static_cast<uint8_t>(clean[i + 2])];
        uint8_t d = DECODE_TABLE[static_cast<uint8_t>(clean[i + 3])];

        if (a == 0xFF || b == 0xFF || c == 0xFF || d == 0xFF)
        {
            throw std::invalid_argument("Invalid base64 character");
        }

        uint32_t triple = (static_cast<uint32_t>(a) << 18) |
                          (static_cast<uint32_t>(b) << 12) |
                          (static_cast<uint32_t>(c) << 6) |
                          static_cast<uint32_t>(d);

        output += static_cast<char>((triple >> 16) & 0xFF);

        if (clean[i + 2] != '=')
        {
            output += static_cast<char>((triple >> 8) & 0xFF);
        }

        if (clean[i + 3] != '=')
        {
            output += static_cast<char>(triple & 0xFF);
        }
    }

    return output;
}

} // namespace ap
