#include "../salp/common.hpp"
#include "../config/daemonSettings.hpp"

#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <string>
#include <iostream>


namespace server {
    // Load the settings on every connection instead of caching them in a
    // process-global. jmxd is long-running, so a cached address/port would
    // keep using the old values until the daemon restarted (and restarting
    // jmxd removes /run/jmx, including the active session file).
    inline int connectToServer() {
        DaemonSettings settings;

        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) {
            std::cerr << "Socket creation error" << std::endl;
            return -1;
        }

        sockaddr_in server_address {};
        server_address.sin_family = AF_INET;
        server_address.sin_port = htons(settings.server_port.empty() ? 8080 : std::stoi(settings.server_port));

        if (inet_pton(AF_INET, settings.server_address.c_str(), &server_address.sin_addr) <= 0) {
            std::cerr << "Invalid address/ Address not supported" << std::endl;
            close(sock);
            return -1;
        }

        struct timeval timeout;
        timeout.tv_sec = 30;
        timeout.tv_usec = 0;

        if (setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout)) < 0) {
            std::cerr << "Error setting socket timeout" << std::endl;
            close(sock);
            return -1;
        }

        if (connect(sock, (struct sockaddr*)&server_address, sizeof(server_address)) < 0) {
            std::cerr << "Connection Failed" << std::endl;
            close(sock);
            return -1;
        }
        
        return sock;
    }

}
