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
#include "./config/daemonSettings.hpp"
#include "./session/sessionManager.hpp"

#include <csignal>
#include <cstring>
#include <string>
#include <sys/socket.h>
#include <syslog.h>
#include <unistd.h>
#include <thread>
#include <condition_variable>
#include <mutex>
#include <atomic>

namespace {

    volatile sig_atomic_t g_stop = 0;
    void onSignal(int) { g_stop = 1; }

    std::string handleCommands(const nlohmann::json& request) {
        std::string command = request.value("action", "");
        
        if (command == "hello") {
            return command_handler::handleHello();
        } else if (command == "start") {
            return command_handler::handleStart(request);
        } else if (command == "end") {
            return command_handler::handleEnd();
        } else if (command == "get_questions") {
            return command_handler::handleGetQuestions();
        } else if (command == "get_stats") {
            return command_handler::handleGetStats();
        } else if (command == "submit") {
            return command_handler::handleSubmit(request);
        }
        
        return "ERROR: Unknown command";
    }

    // Thread control mechanisms
    std::condition_variable cleanup_cv;
    std::mutex cleanup_cv_mtx;
    std::atomic<bool> stop_cleanup_thread(false);

    void session_cleanup_worker(SessionManager& manager, std::chrono::minutes check_interval) {
        while (!stop_cleanup_thread) {
            std::unique_lock<std::mutex> lock(cleanup_cv_mtx);
            
            if (cleanup_cv.wait_for(lock, check_interval, [] { return stop_cleanup_thread.load(); })) {
                break; 
            }

            std::string error {};
            if (manager.check_and_cleanup(error)) {
                syslog(LOG_INFO, "[Session Cleanup] Expired session tracking data successfully wiped.");
            } else if (!error.empty()) {
                syslog(LOG_ERR, "[Session Cleanup Error] %s", error.c_str());
            }

            
        }
    }

}

int main() {
    openlog("jmxd", LOG_PID | LOG_CONS, LOG_DAEMON);
    syslog(LOG_INFO, "starting, listening on %s", jmx::kSocketPath);

    DaemonSettings settings;
    settings.load_from_system("/etc/jmxd/jmxd.conf");

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

    // Cleanup thread
    SessionManager session_manager;
    std::chrono::minutes run_interval(5);
    std::thread cleanup_thread(session_cleanup_worker, std::ref(session_manager), run_interval);


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
            if (request.is_discarded()) {
                syslog(LOG_WARNING, "malformed JSON request, dropping connection");
                close(clientFd);
                continue;
            }
            std::string response = handleCommands(request);
            jmx::sendMessage(clientFd, response);
        } else {
            syslog(LOG_WARNING, "malformed or oversized request, dropping connection");
        }
        close(clientFd);                         
    }

    syslog(LOG_INFO, "shutting down");
    close(listenFd);
    unlink(jmx::kSocketPath);
    stop_cleanup_thread = true;
    cleanup_cv.notify_all();
    if (cleanup_thread.joinable()) {
        cleanup_thread.join();
    }
    closelog();
    return 0;
}
