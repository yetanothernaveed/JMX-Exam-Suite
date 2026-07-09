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

#include "common.hpp"

#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <grp.h>
#include <pwd.h>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <syslog.h>
#include <unistd.h>

namespace {

volatile sig_atomic_t g_stop = 0;
void onSignal(int) { g_stop = 1; }

// Logs the connecting process's real credentials. Useful today for
// auditing, and this is where you'd add uid/gid-based authorization
// checks once commands do more than say hello.
void logPeerCredentials(int clientFd) {
    struct ucred cred{};
    socklen_t len = sizeof(cred);
    if (getsockopt(clientFd, SOL_SOCKET, SO_PEERCRED, &cred, &len) != 0) {
        syslog(LOG_WARNING, "could not read peer credentials: %s", strerror(errno));
        return;
    }
    struct passwd* pw = getpwuid(cred.uid);
    syslog(LOG_INFO, "connection from uid=%u (%s) gid=%u pid=%d",
           cred.uid, pw ? pw->pw_name : "?", cred.gid, cred.pid);
}

// The one command the daemon currently understands. Keep this as an
// explicit if/else (or switch) allowlist -- never dispatch based on
// arbitrary client-supplied strings interpreted as code, paths, or
// shell fragments.
std::string handleCommand(const std::string& command) {
    if (command == "hello") {
        return "Hi!";
    }
    return "ERROR: unknown command";
}

int createListenSocket(const char* path) {
    unlink(path); // clean start every boot/restart

    int fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) {
        syslog(LOG_ERR, "socket() failed: %s", strerror(errno));
        return -1;
    }

    sockaddr_un addr{};
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);

    // Restrict the socket file's default mode; refined below.
    mode_t oldUmask = umask(0077);
    int rc = bind(fd, reinterpret_cast<sockaddr*>(&addr), sizeof(addr));
    umask(oldUmask);
    if (rc != 0) {
        syslog(LOG_ERR, "bind(%s) failed: %s", path, strerror(errno));
        close(fd);
        return -1;
    }

    // If a dedicated "jmx" group exists, let its members connect too;
    // otherwise only root (the daemon's own uid) can.
    struct group* grp = getgrnam("jmx");
    if (grp) {
        if (chown(path, 0, grp->gr_gid) != 0) {
            syslog(LOG_WARNING, "chown(%s) failed: %s", path, strerror(errno));
        }
        chmod(path, 0660);
    } else {
        chmod(path, 0600);
    }

    if (listen(fd, 16) != 0) {
        syslog(LOG_ERR, "listen() failed: %s", strerror(errno));
        close(fd);
        return -1;
    }
    return fd;
}

} // namespace

int main() {
    openlog("jmxd", LOG_PID | LOG_CONS, LOG_DAEMON);
    syslog(LOG_INFO, "starting, listening on %s", jmx::kSocketPath);

    // signal(SIGTERM, onSignal);
    // signal(SIGINT, onSignal);
    // signal(SIGPIPE, SIG_IGN); // a client disconnecting shouldn't kill us
    struct sigaction sa{};
    sa.sa_handler = onSignal;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0; // CRITICAL: Explicitly do NOT set SA_RESTART

    if (sigaction(SIGTERM, &sa, nullptr) < 0) {
        syslog(LOG_ERR, "Failed to register SIGTERM handler");
        return 1;
    }
    if (sigaction(SIGINT, &sa, nullptr) < 0) {
        syslog(LOG_ERR, "Failed to register SIGINT handler");
        return 1;
    }

    int listenFd = createListenSocket(jmx::kSocketPath);
    if (listenFd < 0) {
        syslog(LOG_ERR, "failed to create listening socket, exiting");
        return 1;
    }

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

        logPeerCredentials(clientFd);

        std::string request;
        if (jmx::recvMessage(clientFd, request)) {
            std::string response = handleCommand(request);
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
