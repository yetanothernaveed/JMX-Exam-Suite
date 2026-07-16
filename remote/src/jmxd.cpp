// jmxd.cpp - privileged background daemon for the jmx tool.
//
// Listens on a Unix domain socket for commands sent by the unprivileged
// `jmx` CLI (normally invoked from inside a firejail sandbox) and
// executes a small, explicit allowlist of operations on their behalf.
//
// Security notes for anyone extending this:
//  - Only ever add new commands to the allowlist in handleCommand().
//    Never build a shell command string out of client input and hand
//    it to system()/popen() -- that turns "higher privilege daemon"
//    into "root shell for anyone who can open the socket".
//  - SO_PEERCRED gives you the real uid/gid/pid of the connecting
//    process. Use it for authorization decisions and audit logging as
//    the command set grows past "hello".
//  - The socket file's permissions (set below) are the actual access
//    control boundary. Keep them as tight as your use case allows.

#include "./headers/common.hpp"
#include "./handlers/commandHandler.hpp"
#include "./headers/createUnixSocket.hpp"
#include "./headers/credentials.hpp"
#include "./lib/json.hpp"

#include <csignal>
#include <cstring>
#include <string>
#include <sys/socket.h>
#include <syslog.h>
#include <unistd.h>

namespace {

volatile sig_atomic_t g_stop = 0;
void onSignal(int) { g_stop = 1; }

// The one command the daemon currently understands. Keep this as an
// explicit if/else (or switch) allowlist -- never dispatch based on
// arbitrary client-supplied strings interpreted as code, paths, or
// shell fragments.
std::string handleCommand(int& serverFd, const nlohmann::json& request) {
    std::string command = request.value("action", "");
    
    if (command == "hello") {
        return command_handler::handleHello();
    } else if (command == "start") {
        return command_handler::handleStart(
            serverFd, 
            request
        );
    }
    
    return "ERROR: Unknown command";
}

}

int main() {
    openlog("jmxd", LOG_PID | LOG_CONS, LOG_DAEMON);
    syslog(LOG_INFO, "starting, listening on %s", jmx::kSocketPath);

    struct sigaction sa{};
    sa.sa_handler = onSignal;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;

    if (sigaction(SIGTERM, &sa, nullptr) < 0) {
        syslog(LOG_ERR, "Failed to register SIGTERM handler");
        return 1;
    }
    if (sigaction(SIGINT, &sa, nullptr) < 0) {
        syslog(LOG_ERR, "Failed to register SIGINT handler");
        return 1;
    }

    int listenFd = jmx_unix_socket::createListenSocket(jmx::kSocketPath);
    if (listenFd < 0) {
        syslog(LOG_ERR, "failed to create listening socket, exiting");
        return 1;
    }


    // Connects to the server
    // Will be initialized only if requested.
    int serverFd {};

    // Single-threaded accept loop: simple and sufficient for a small
    // command set. If you need to handle slow/concurrent clients
    // later, hand each accepted fd to a thread or a fork()'d child.
    while (!g_stop) {
        int clientFd = accept(listenFd, nullptr, nullptr);
        if (clientFd < 0) {
            if (g_stop) break;

            if (errno == EINTR) continue;
            
            syslog(LOG_WARNING, "accept() failed: %s", strerror(errno));
            continue;
        }

        credentials::logPeerCredentials(clientFd);

        std::string payload;
        if (jmx::recvMessage(clientFd, payload)) {
            nlohmann::json request = nlohmann::json::parse(payload, nullptr, false);
            std::string response = handleCommand(serverFd, request);
            jmx::sendMessage(clientFd, response);
        } else {
            syslog(LOG_WARNING, "malformed or oversized request, dropping connection");
        }
        close(clientFd);                         
    }

    syslog(LOG_INFO, "shutting down");
    close(listenFd);
    unlink(jmx::kSocketPath);
    closelog();
    return 0;
}
