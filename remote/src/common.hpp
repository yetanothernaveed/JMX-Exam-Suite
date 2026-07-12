#pragma once

// common.hpp - shared constants and wire-protocol helpers for jmx/jmxd.
//
// Wire format: a 4-byte big-endian length prefix followed by that many
// bytes of UTF-8 payload. This is simple, unambiguous, and leaves room
// to grow (e.g. turning the payload into small JSON objects) without
// changing the framing logic.

#include <arpa/inet.h>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace jmx {

// Path of the Unix domain socket used for CLI <-> daemon communication.
// Lives under /run (tmpfs), recreated on every boot. The containing
// directory's ownership/permissions are what actually control who may
// connect -- see jmxd.service's RuntimeDirectory= setting.
inline constexpr const char* kSocketPath = "/run/jmx/jmx.sock";

// Upper bound on a single message. Keeps a misbehaving or malicious
// peer from making the daemon allocate unbounded memory.
inline constexpr uint32_t kMaxMessageSize = 64 * 1024; // 64 KiB

inline bool readFull(int fd, void* buf, size_t len) {
    auto* p = static_cast<uint8_t*>(buf);
    size_t remaining = len;
    while (remaining > 0) {
        ssize_t n = ::read(fd, p, remaining);
        if (n == 0) return false;          // peer closed the connection
        if (n < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        p += n;
        remaining -= static_cast<size_t>(n);
    }
    return true;
}

inline bool writeFull(int fd, const void* buf, size_t len) {
    const auto* p = static_cast<const uint8_t*>(buf);
    size_t remaining = len;
    while (remaining > 0) {
        ssize_t n = ::write(fd, p, remaining);
        if (n < 0) {
            if (errno == EINTR) continue;
            return false;
        }
        p += n;
        remaining -= static_cast<size_t>(n);
    }
    return true;
}

// Sends a single message to the peer. Returns false on I/O error or if the payload is too large.
inline bool sendMessage(int fd, const std::string& payload) {
    if (payload.size() > kMaxMessageSize) return false;
    uint32_t len = htonl(static_cast<uint32_t>(payload.size()));
    if (!writeFull(fd, &len, sizeof(len))) return false;
    if (!payload.empty() && !writeFull(fd, payload.data(), payload.size())) return false;
    return true;
}

// Returns false on I/O error or if the peer declares a size over the limit.
inline bool recvMessage(int fd, std::string& out) {
    uint32_t lenNet = 0;
    if (!readFull(fd, &lenNet, sizeof(lenNet))) return false;
    uint32_t len = ntohl(lenNet);
    if (len > kMaxMessageSize) return false;
    out.resize(len);
    if (len > 0 && !readFull(fd, out.data(), len)) return false;
    return true;
}

} // namespace jmx
