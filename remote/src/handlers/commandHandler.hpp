#pragma once

#include "../headers/connectToServer.hpp"
#include "../lib/json.hpp"

#include <string>

namespace command_handler {
    inline std::string handleHello() {
        return "Hi!";
    }

    inline std::string handleStart(int& serverFd, const nlohmann::json& payload) {
        serverFd = server::connectToServer();
        
        std::string payloadStr = payload.dump();
        
        jmx::sendMessage(serverFd, payloadStr);
        std::string response {};
        if (jmx::recvMessage(serverFd, response)) {
            return response;
        } else {
            return "ERROR: failed to receive response from server"; 
        }
    }
}
