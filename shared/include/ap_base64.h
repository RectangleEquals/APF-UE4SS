#pragma once

#include <string>

namespace ap
{

// Base64 encode a raw string to a base64 string
std::string base64_encode(const std::string &input);

// Base64 decode a base64 string to raw bytes
std::string base64_decode(const std::string &input);

} // namespace ap
