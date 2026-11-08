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

    // Create `dir_path` if needed, or remove everything inside it if it already
    // exists. Filesystem errors are reported through `error` instead of being
    // thrown so callers inside the daemon can fail gracefully.
    inline bool reset_directory(const fs::path& dir_path, std::string& error) {
        std::error_code ec;

        // symlink_status() avoids following a symlink and deleting the
        // contents of an unrelated target directory.
        fs::file_status status = fs::symlink_status(dir_path, ec);
        if (ec) {
            if (ec == std::errc::no_such_file_or_directory) {
                // status() reports a missing path as an error, unlike exists().
                ec.clear();
                status = fs::file_status(fs::file_type::not_found);
            } else {
                error = "Could not inspect '" + dir_path.string() + "': " + ec.message();
                return false;
            }
        }

        if (!fs::exists(status)) {
            fs::create_directories(dir_path, ec);
            if (ec) {
                error = "Could not create '" + dir_path.string() + "': " + ec.message();
                return false;
            }
            return true;
        }

        if (!fs::is_directory(status)) {
            error = "'" + dir_path.string() + "' exists but is not a directory";
            return false;
        }

        fs::directory_iterator entry_it(dir_path, ec);
        if (ec) {
            error = "Could not read '" + dir_path.string() + "': " + ec.message();
            return false;
        }

        const fs::directory_iterator end_it;
        while (entry_it != end_it) {
            fs::remove_all(entry_it->path(), ec);
            if (ec) {
                error = "Could not remove '" + entry_it->path().string() + "': " + ec.message();
                return false;
            }

            entry_it.increment(ec);
            if (ec) {
                error = "Could not continue reading '" + dir_path.string() + "': " + ec.message();
                return false;
            }
        }

        return true;
    }

    inline bool write_file_to_directory(const fs::path& dir_path, const std::string& filename, const std::string& content) {
        std::error_code ec;

        if (!fs::exists(dir_path, ec)) {
            if (ec) {
                std::cerr << "Failed to inspect directory: " << dir_path
                          << " | Reason: " << ec.message() << std::endl;
                return false;
            }

            fs::create_directories(dir_path, ec);
            if (ec) {
                std::cerr << "Failed to create directory: " << dir_path
                          << " | Reason: " << ec.message() << std::endl;
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

        if (!ofs) {
            std::cerr << "Failed to write file: " << file_path << std::endl;
            return false;
        }

        return true;
    }

} // namespace exam_workspace_handler


