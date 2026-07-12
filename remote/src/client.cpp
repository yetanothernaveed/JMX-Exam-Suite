// jmx.cpp - unprivileged CLI client.
//
// Usage:
//   jmx hello

#include "common.hpp"

#include <cstring>
#include <iostream>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

namespace {

int connectToDaemon(const char* path) {
    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        perror("socket");
        return -1;
    }
    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);

    if (connect(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        perror("connect");
        close(fd);
        return -1;
    }
    return fd;
}

void printUsage(const char* argv0) {
    std::cerr << "usage: " << argv0 << " <command>\n"
              << "commands:\n"
              << "  hello   ask the jmxd daemon to say hi\n";
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        printUsage(argv[0]);
        return 2;
    }

    std::string command = argv[1];

    int fd = connectToDaemon(jmx::kSocketPath);
    if (fd < 0) {
        std::cerr << "jmx: could not connect to jmxd at " << jmx::kSocketPath << "\n"
                  << "     is the daemon running? (systemctl status jmxd)\n";
        return 1;
    }

    if (!jmx::sendMessage(fd, command)) {
        std::cerr << "jmx: failed to send command to daemon\n";
        close(fd);
        return 1;
    }

    std::string response;
    if (!jmx::recvMessage(fd, response)) {
        std::cerr << "jmx: no (or malformed) response from daemon\n";
        close(fd);
        return 1;
    }

    close(fd);
    std::cout << response << std::endl;
    
    return response.starts_with("ERROR") ? 1 : 0; // For C++ 20
}
