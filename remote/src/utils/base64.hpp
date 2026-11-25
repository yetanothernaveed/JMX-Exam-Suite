#pragma once

// Minimal, strict RFC 4648 base64 decoder for question assets.
//
// The SALP wire format carries JSON text, so binary question files are sent as
// base64 strings by the server and decoded here before being written into the
// exam workspace. This decoder is intentionally strict: malformed payloads are
// rejected instead of producing a silently corrupted PDF or image.

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

namespace jmx::base64 {

inline int six_bit_value(unsigned char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

// Decodes `input` into `out`. Returns false and fills `error` for any invalid
// input. `max_bytes` bounds the decoded size (the caller passes the SALP
// message limit, which is a natural ceiling for a decoded payload).
inline bool decode(std::string_view input, std::vector<std::uint8_t>& out,
                   std::string& error, std::size_t max_bytes) {
    out.clear();

    if (input.empty()) {
        return true;
    }

    if (input.size() % 4 != 0) {
        error = "base64 payload length is not a multiple of 4";
        return false;
    }

    const std::size_t blocks = input.size() / 4;
    if (blocks * 3 > max_bytes) {
        error = "base64 payload exceeds the maximum allowed size";
        return false;
    }

    out.reserve(blocks * 3);

    for (std::size_t i = 0; i < input.size(); i += 4) {
        const bool last_block = (i + 4 == input.size());
        const unsigned char c[4] = {
            static_cast<unsigned char>(input[i]),
            static_cast<unsigned char>(input[i + 1]),
            static_cast<unsigned char>(input[i + 2]),
            static_cast<unsigned char>(input[i + 3])
        };

        int v[4] = {0, 0, 0, 0};
        for (int j = 0; j < 4; ++j) {
            if (c[j] == '=') {
                if (!last_block || j < 2) {
                    error = "unexpected '=' padding in base64 payload";
                    return false;
                }
            } else {
                v[j] = six_bit_value(c[j]);
                if (v[j] < 0) {
                    error = "invalid character in base64 payload";
                    return false;
                }
            }
        }

        if (c[1] == '=' || (c[2] == '=' && c[3] != '=')) {
            error = "invalid base64 padding";
            return false;
        }

        // Reject non-canonical encodings: the unused low bits of the final
        // octet(s) must be zero.
        if (last_block && c[3] == '=' && (v[2] & 0x03) != 0) {
            error = "non-canonical base64 payload (unused bits are set)";
            return false;
        }
        if (last_block && c[2] == '=' && (v[1] & 0x0F) != 0) {
            error = "non-canonical base64 payload (unused bits are set)";
            return false;
        }

        const std::uint32_t bits =
            (static_cast<std::uint32_t>(v[0]) << 18) |
            (static_cast<std::uint32_t>(v[1]) << 12) |
            (static_cast<std::uint32_t>(v[2]) << 6) |
            static_cast<std::uint32_t>(v[3]);

        out.push_back(static_cast<std::uint8_t>((bits >> 16) & 0xFF));
        if (c[2] != '=') {
            out.push_back(static_cast<std::uint8_t>((bits >> 8) & 0xFF));
        }
        if (c[3] != '=') {
            out.push_back(static_cast<std::uint8_t>(bits & 0xFF));
        }
    }

    return true;
}

} // namespace jmx::base64
