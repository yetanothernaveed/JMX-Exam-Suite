#pragma once

#include "configManagar.hpp"
#include "../headers/common.hpp"
#include <string>

struct DaemonSettings {
    std::string socket_directory = jmx::kSocketPath;
    std::string workspace_directory = "/home/examkiosk/exam_workspace";
    std::string server_address = "172.16.0.26";
    std::string server_port = "8080";


    void load_from_system(const std::string& path) {
        ConfigManager wrapper;
        if (wrapper.load(path)) {
            // Override defaults only if the file exists and has values
            socket_directory = wrapper.get("socket_directory", socket_directory);
            workspace_directory = wrapper.get("workspace_directory", workspace_directory);
            server_address = wrapper.get("server_address", server_address);
            server_port = wrapper.get("server_port", server_port);
        } else {
            // File didn't exist, create it with our defaults
            wrapper.set("socket_directory", socket_directory);
            wrapper.set("workspace_directory", workspace_directory);
            wrapper.set("server_address", server_address);
            wrapper.set("server_port", server_port);
            wrapper.save(path);
        }
    }
};
