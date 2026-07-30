#pragma once

#include <sys/socket.h>    // socket(), bind(), listen(), sockaddr
#include <sys/un.h>        // sockaddr_un, AF_UNIX
#include <sys/stat.h>      // umask(), chmod(), mode_t
#include <sys/types.h>     // miscellaneous system data types
#include <unistd.h>        // close(), unlink(), chown()
#include <grp.h>           // getgrnam(), struct group
#include <syslog.h>        // syslog(), LOG_ERR, LOG_WARNING

#include <cerrno>          // errno
#include <cstring>         // strerror(), strncpy()

namespace jmx_unix_socket {
    inline int createListenSocket(const char* path) {
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

}
