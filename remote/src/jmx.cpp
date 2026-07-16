// jmx.cpp - unprivileged CLI client.
//
// Usage:
//   jmx hello

#include "./headers/common.hpp"
#include "./lib/CLI11.hpp"

// Commands
#include "./commands/HelloCommand.hpp"
#include "./commands/StartCommand.hpp"

#include <cstring>
#include <iostream>
#include <string>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <memory>
#include <vector>

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

} // namespace

int main(int argc, char** argv) {
    CLI::App app{"jmx - Seamless onsite coding exams"};
    // app.require_subcommand(1);

    std::vector<std::unique_ptr<Command>> commands;
    commands.push_back(std::make_unique<HelloCommand>());
    commands.push_back(std::make_unique<StartCommand>());

    for (auto& cmd : commands) {
        cmd->setup(app);
    }

    CLI11_PARSE(app, argc, argv);

    std::string payload;

    for (const auto& cmd : commands) {
        if (cmd->is_called()) {
            payload = cmd->serialize().dump();
            break;
        }
    }


    int fd = connectToDaemon(jmx::kSocketPath);
    if (fd < 0) {
        std::cerr << "jmx: could not connect to jmxd at " << jmx::kSocketPath << "\n"
                  << "     is the daemon running? (systemctl status jmxd)\n";
        return 1;
    }

    if (!jmx::sendMessage(fd, payload)) {
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
