#pragma once

#include "../config/daemonSettings.hpp"
#include "../handlers/examWorkspaceHandler.hpp"

#include <filesystem>
#include <string>
#include <iostream>
#include <chrono>

class SessionManager {
    private:
        // path to session file
        std::filesystem::path session_file_path;
        std::filesystem::path session_directory_path;
        int session_duration_in_hours;

        mutable std::mutex session_mutex;

        std::string trim(const std::string& str) {
            size_t first = str.find_first_not_of(" \t\r\n");
            if (first == std::string::npos) return "";
            size_t last = str.find_last_not_of(" \t\r\n");
            return str.substr(first, (last - first + 1));
        }

        bool load_session_internal() {
            if (!std::filesystem::exists(session_file_path)) {
                return false;
            }

            std::ifstream session_file(session_file_path);
            if (!session_file.is_open()) {
                std::cerr << "Failed to open session file: " << session_file_path << std::endl;
                return false;
            }

            std::string line;
            while (std::getline(session_file, line)) {
                auto delimiter_pos = line.find('=');
                if (delimiter_pos != std::string::npos) {
                    std::string key = line.substr(0, delimiter_pos);
                    std::string value = line.substr(delimiter_pos + 1);
                    
                    key = trim(key);
                    value = trim(value);

                    if (key == "student_id") {
                        student_id = value;
                    } else if (key == "student_name") {
                        student_name = value;
                    } else if (key == "exam_id") {
                        exam_id = value;
                    }
                }
            }

            session_file.close();
            return true;
        }

        std::string student_id;
        std::string student_name;
        std::string exam_id;

    public:
        SessionManager() {
            DaemonSettings settings;
            session_directory_path = std::filesystem::path(settings.socket_directory) / "sessions";
            session_file_path = session_directory_path / "current_session.txt";
            session_duration_in_hours = std::stoi(settings.session_duration_in_hours);
            
            std::filesystem::create_directories(session_file_path.parent_path());

            std::lock_guard<std::mutex> lock(session_mutex);
            load_session_internal();
        }

        std::string get_student_id() const {
            std::lock_guard<std::mutex> lock(session_mutex);
            return student_id;
        }

        std::string get_student_name() const {
            std::lock_guard<std::mutex> lock(session_mutex);
            return student_name;
        }

        std::string get_exam_id() const {
            std::lock_guard<std::mutex> lock(session_mutex);
            return exam_id;
        }

        bool create_session(std::string& error, std::string s_id, std::string s_name, std::string exam_id) {
            std::lock_guard<std::mutex> lock(session_mutex);
            
            // If a session file is found, ask user to delete it first
            if (std::filesystem::exists(session_file_path)) {
                error = "ERROR: A session already exists. To exit the current session, use command:\n jmx end\n";
                return false;
            }

            std::ofstream session_file(session_file_path);
            if (!session_file.is_open()) {
                error = "ERROR: Failed to create session file: " + session_file_path.string();
                std::cerr << "Failed to create session file: " << session_file_path << std::endl;
                return false;
            }

            // Write session details to the file
            session_file << "student_id = " << s_id << std::endl;
            session_file << "student_name = " << s_name << std::endl;
            session_file << "exam_id = " << exam_id << std::endl;

            session_file.close();

            this->student_id = s_id;
            this->student_name = s_name;
            this->exam_id = exam_id;

            return true;
        }

        bool delete_session(std::string& error) {
            std::lock_guard<std::mutex> lock(session_mutex);

            if (!std::filesystem::exists(session_file_path)) {
                error = "ERROR: No active session found.";
                return false;
            }

            std::error_code ec;
            std::filesystem::remove(session_file_path, ec);
            if (ec) {
                error = "ERROR: Failed to delete session file: " + ec.message();
                return false;
            }

            this->student_id.clear();
            this->student_name.clear();
            this->exam_id.clear();

            return true;
        }

        bool check_session_exists() const {
            std::lock_guard<std::mutex> lock(session_mutex);
            return std::filesystem::exists(session_file_path);
        }

        // For cleanup thread
        // DEADCODE: Could be repurposed for a cleanup thread that removes expired sessions.
        // Remove after final resign decision.
        bool check_and_cleanup(std::string& error) {
            std::lock_guard<std::mutex> lock(session_mutex);

            if (!std::filesystem::exists(session_file_path)) {
                return false;
            }

            std::error_code ec;
            auto last_write = std::filesystem::last_write_time(session_file_path, ec);
            if (ec) {
                error = "Failed to read session file timestamp: " + ec.message();
                return false;
            }

            auto now = std::filesystem::file_time_type::clock::now();
            auto file_age = std::chrono::duration_cast<std::chrono::hours>(now - last_write);

            
            if (file_age.count() >= session_duration_in_hours) {
                std::cout << "[Test Log] File age is " << file_age.count() 
                << " hours. Expired! Deleting..." << std::endl;

                std::filesystem::remove(session_file_path, ec);
                
                if (!exam_workspace_handler::clear_directory()) {
                    error = "Failed to clear exam workspace directory.";
                    return false;
                }

                this->student_id.clear();
                this->student_name.clear();
                this->exam_id.clear();
                return true; 
            } 

            return false;
        }
};
