#pragma once

#include <iostream>
#include <fstream>
#include <string>
#include <map>
#include <algorithm>
#include <filesystem>
#include <syslog.h>

namespace fs = std::filesystem;

class ConfigManager {
private:
    std::map<std::string, std::string> config_data;

    // Helper to trim whitespace from strings
    std::string trim(const std::string& str) {
        size_t first = str.find_first_not_of(" \t\r\n");
        if (first == std::string::npos) return "";
        size_t last = str.find_last_not_of(" \t\r\n");
        return str.substr(first, (last - first + 1));
    }

public:
    // Read the config file into memory
    bool load(const fs::path& file_path) {
        std::ifstream file(file_path);
        if (!file.is_open()) {
            std::cerr << "Failed to open config file for reading: " << file_path << std::endl;
            return false;
        }

        config_data.clear();
        std::string line;
        while (std::getline(file, line)) {
            line = trim(line);
            
            // Skip empty lines and comments
            if (line.empty() || line[0] == '#') continue;

            size_t delimiter_pos = line.find('=');
            if (delimiter_pos == std::string::npos) continue; // Invalid line format

            std::string key = trim(line.substr(0, delimiter_pos));
            std::string value = trim(line.substr(delimiter_pos + 1));
            
            if (!key.empty()) {
                config_data[key] = value;
            }
        }
        return true;
    }

    // Retrieve a value by key, providing a fallback default value
    std::string get(const std::string& key, const std::string& default_value = "") const {
        auto it = config_data.find(key);
        if (it != config_data.end()) {
            return it->second;
        }
        return default_value;
    }

    // Set or Update a value in memory
    void set(const std::string& key, const std::string& value) {
        config_data[key] = value;
    }

    // Write the current in-memory configurations back to the file
    bool save(const fs::path& file_path) {
        // Create folder and file if they don't exist
        if (!fs::exists(file_path.parent_path())) {
            std::cout << "Creating directory: " << file_path.parent_path() << std::endl;
            syslog(LOG_INFO, "/etc/jmxd does not exist.\nCreating directory: %s", file_path.parent_path().c_str());
            fs::create_directories(file_path.parent_path());
        }
        
        std::ofstream file(file_path, std::ios::out | std::ios::trunc);


        if (!file.is_open()) {
            std::cerr << "Failed to open config file for writing: " << file_path << std::endl;
            return false;
        }

        file << "# Automatically generated daemon configuration\n\n";
        for (const auto& [key, value] : config_data) {
            file << key << " = " << value << "\n";
        }
        return true;
    }
};
