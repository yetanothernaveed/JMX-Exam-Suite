#pragma once

#include "../config/daemonSettings.hpp"

#include <iostream>
#include <filesystem>
#include <fstream>
#include <string>
#include <system_error>

namespace fs = std::filesystem;

namespace exam_workspace_handler {
    inline bool clear_directory() {
        DaemonSettings settings;
        fs::path dir_path = fs::path(settings.workspace_directory);
        std::error_code ec;

        if (!fs::exists(dir_path, ec) || !fs::is_directory(dir_path, ec)) {
            std::cerr << "Target path is not a valid directory: " << dir_path << std::endl;
            return false;
        }

        bool all_cleared = true;

        for (const auto& entry : fs::directory_iterator(dir_path, ec)) {
            if (ec) {
                std::cerr << "Error while reading directory entries: " << ec.message() << std::endl;
                return false;
            }

            std::error_code remove_ec;
            
            fs::remove_all(entry.path(), remove_ec);

            if (remove_ec) {
                std::cerr << "Failed to delete item: " << entry.path() 
                        << "Reason: " << remove_ec.message() << std::endl;
                
                all_cleared = false; 
            }
        }

        if (ec) {
            std::cerr << "Directory iteration ended unexpectedly: " << ec.message() << std::endl;
            return false;
        }

        return all_cleared;
    }

    inline bool write_file_to_directory(const fs::path& dir_path, const std::string& filename, const std::string& content) {
        if (!fs::exists(dir_path)) {
            std::error_code ec;
            if (!fs::create_directories(dir_path, ec)) {
                std::cerr << "Failed to write to directory: " << dir_path 
                        << " | Reason: " << "No such directory" << std::endl;
                return false;
            }
        }

        fs::path file_path = dir_path / filename; 

        std::ofstream ofs(file_path, std::ios::out | std::ios::trunc);
        if (!ofs.is_open()) {
            std::cerr << "Failed to create file: " << file_path << std::endl;
            return false;
        }

        ofs << content;
        ofs.close();
        return true;
    }

} // namespace exam_workspace_handler


