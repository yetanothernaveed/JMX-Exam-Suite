#pragma once

#include "configManager.hpp"
#include "../salp/common.hpp"
#include <string>

struct DaemonSettings {
    std::string socket_directory = "/run/jmx";
    std::string workspace_directory = "/home/naveed/exam_workspace"; // Update this for production
    std::string server_address = "127.0.0.1";
    std::string server_port = "8080";
    std::string session_duration_in_hours = "2";


    void load_from_system(const std::string& path) {
        ConfigManager wrapper;
        if (wrapper.load(path)) {
            // Override defaults only if the file exists and has values
            socket_directory = wrapper.get("socket_directory", socket_directory);
            workspace_directory = wrapper.get("workspace_directory", workspace_directory);
            server_address = wrapper.get("server_address", server_address);
            server_port = wrapper.get("server_port", server_port);
            session_duration_in_hours = wrapper.get("session_duration_in_hours", session_duration_in_hours);
        } else {
            // File didn't exist, create it with our defaults
            wrapper.set("socket_directory", socket_directory);
            wrapper.set("workspace_directory", workspace_directory);
            wrapper.set("server_address", server_address);
            wrapper.set("server_port", server_port);
            wrapper.set("session_duration_in_hours", session_duration_in_hours);
            wrapper.save(path);
        }
    }
};
