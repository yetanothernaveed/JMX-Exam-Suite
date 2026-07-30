#include "../salp/common.hpp"
#include "../config/daemonSettings.hpp"

#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <string>
#include <iostream>


namespace server {
    DaemonSettings settings;
    const char* IP = settings.server_address.c_str();
    const int PORT = settings.server_port.empty() ? 8080 : std::stoi(settings.server_port);

    inline int connectToServer() {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) {
            std::cerr << "Socket creation error" << std::endl;
            return -1;
        }

        sockaddr_in server_address {};
        server_address.sin_family = AF_INET;
        server_address.sin_port = htons(PORT);

        if (inet_pton(AF_INET, IP, &server_address.sin_addr) <= 0) {
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
