#pragma once

#include <syslog.h> 
#include <pwd.h>
#include <sys/socket.h>
#include <cerrno>
#include <cstring>
#include <unistd.h>

namespace credentials {
    // Logs the connecting process's real credentials. Useful today for
    // auditing, and this is where you'd add uid/gid-based authorization
    // checks once commands do more than say hello.
    inline void logPeerCredentials(int clientFd) {
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

}
