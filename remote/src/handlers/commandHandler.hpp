#pragma once

#include "../utils/base64.hpp"
#include "../utils/connectToServer.hpp"
#include "../lib/json.hpp"
#include "../session/sessionManager.hpp"

#include <array>
#include <cstdint>
#include <string>
#include <string_view>
#include <unistd.h>
#include <climits>
#include <vector>

namespace command_handler {
    // File types that may be placed in the exam workspace as question assets.
    inline bool is_supported_question_extension(const std::string& extension) {
        static constexpr std::array<std::string_view, 14> supported = {
            ".md", ".txt", ".java", ".py", ".cpp", ".c", ".h",
            ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"
        };
        for (std::string_view candidate : supported) {
            if (extension == candidate) {
                return true;
            }
        }
        return false;
    }

    // Writes every question returned by the server into <workspace>/<qid>/.
    // Text questions keep their previous behaviour; assets marked with
    // "encoding": "base64" are decoded and written as binary files.
    inline bool writeQuestionFiles(const nlohmann::json& questions, std::string& error) {
        const std::filesystem::path workspace(DaemonSettings().workspace_directory);

        for (const auto& question : questions) {
            const std::string qid = question.value("qid", std::string{});
            if (!exam_workspace_handler::is_safe_path_component(qid)) {
                error = "Server returned an invalid question ID";
                return false;
            }

            std::string extension = question.value("extension", std::string{});
            if (!extension.empty() && extension.front() != '.') {
                extension.insert(extension.begin(), '.');
            }
            if (!is_supported_question_extension(extension)) {
                error = "Server returned an unsupported file extension for question '" + qid + "'";
                return false;
            }

            std::string filename = question.value("filename", std::string{});
            if (filename.empty()) {
                filename = qid + extension;
            }
            if (!exam_workspace_handler::is_safe_path_component(filename) ||
                std::filesystem::path(filename).filename() != filename) {
                error = "Server returned an invalid filename for question '" + qid + "'";
                return false;
            }

            const std::string encoding = question.value("encoding", std::string{"text"});
            // get_ref avoids a second copy of a potentially large base64 string.
            const std::string& content = question.at("content").get_ref<const std::string&>();
            const std::filesystem::path directory = workspace / qid;

            if (encoding == "base64") {
                std::vector<std::uint8_t> bytes;
                std::string decode_error;
                if (!jmx::base64::decode(content, bytes, decode_error, jmx::kMaxMessageSize)) {
                    error = "Failed to decode question asset '" + filename + "': " + decode_error;
                    return false;
                }
                if (!exam_workspace_handler::write_binary_file_to_directory(directory, filename, bytes)) {
                    error = "Failed to write question asset '" + filename + "' to exam workspace";
                    return false;
                }
            } else if (encoding == "text" || encoding == "utf-8") {
                if (!exam_workspace_handler::write_file_to_directory(directory, filename, content)) {
                    error = "Failed to write question '" + filename + "' to exam workspace";
                    return false;
                }
            } else {
                error = "Unsupported encoding '" + encoding + "' for question '" + qid + "'";
                return false;
            }
        }

        return true;
    }


    inline std::string handleHello(const nlohmann::json& request) {
        const nlohmann::json& payload = request.value("payload", nlohmann::json::object());

        if (payload.value("server", false)) {
            int serverFd = server::connectToServer();

            if (serverFd < 0) {
                return 
                    "ERROR: Failed to connect to server.\n"
                    "The server may not be running or is unreachable.\n" 
                    "Contact administrator.\n";
            }

            std::string response {};
            nlohmann::json responseJson {};

            try {
                // Send a simple ping message to the server
                jmx::sendMessage(serverFd, request.dump());
    
                if (!jmx::recvMessage(serverFd, response)) {
                    return "ERROR: failed to receive response from server"; 
                } else {
                    responseJson = nlohmann::json::parse(response);
    
                    if (responseJson["status"] == "ERROR") {
                        return std::string("ERROR: ") + responseJson["message"].get<std::string>();
                    }
                }

            } catch (const std::exception& e) {
                return std::string("ERROR: Exception occurred while communicating with server: ") + e.what();
            }


            return responseJson["message"].get<std::string>();
        }
        
        return "Hi!";
    }

    inline std::string handleStart(const nlohmann::json& payload) {
        SessionManager sessionManager;
        if (sessionManager.check_session_exists()) {
            return 
                "ERROR: A session is already active. Please end the current session before starting new one.\n  Use command `jmx end` to end the current session.";
        }

        int serverFd = server::connectToServer();

        if (serverFd < 0) {
            return "ERROR: Failed to connect to server";
        }
        
        std::string payloadStr = payload.dump();
        std::string response {};
        nlohmann::json responseJson {};
        
        try {
            jmx::sendMessage(serverFd, payloadStr);
    
            if (!jmx::recvMessage(serverFd, response)) {
                return "ERROR: failed to receive response from server"; 
            } else {
                responseJson = nlohmann::json::parse(response);
    
                if (responseJson["status"] == "ERROR") {
                    return std::string("ERROR: ") + responseJson["message"].get<std::string>();
                }
            }
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while communicating with server: ") + e.what();
        }

        // Create session for student
        std::string error;

        if (!sessionManager.create_session(
            error,
            responseJson["payload"]["student_id"],
            responseJson["payload"]["student_name"],
            responseJson["payload"]["exam_id"]
        )) {
            return error;
        }

        try {
            exam_workspace_handler::clear_directory();
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while clearing exam workspace: ") + e.what();
        }
        
        try {
            std::string write_error;
            if (!writeQuestionFiles(responseJson["payload"].value("questions", nlohmann::json::array()), write_error)) {
                return "ERROR: " + write_error;
            }
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while writing questions to exam workspace: ") + e.what();
        }

        std::string response_msg = 
            "\n\n🟢🟢🟢🟢🟢🟢 SUCCESS 🟢🟢🟢🟢🟢🟢🟢\n"
            "Initiated session for student with the following details:\n"
            "Student ID: " + responseJson["payload"]["student_id"].get<std::string>() + "\n"
            "Student Name: " + responseJson["payload"]["student_name"].get<std::string>() + "\n"
            "Exam ID: " + responseJson["payload"]["exam_id"].get<std::string>() + "\n\n"
            "Do your best! Good luck!\n\n";

        return response_msg;
    }

    inline std::string handleEnd() {
        SessionManager sessionManager;
        if (!sessionManager.check_session_exists()) {
            return "ERROR: No active session to end";
        }
        
        int serverFd = server::connectToServer();

        if (serverFd >= 0) {
            // Add student Id and exam Id to payload
            nlohmann::json message = {
                {"action", "end"},
                {"payload", {
                    {"student_id", sessionManager.get_student_id()},
                    {"exam_id", sessionManager.get_exam_id()}
                }}
            };
            
            std::string response {};
            nlohmann::json responseJson;

            try {
                jmx::sendMessage(serverFd, message.dump());
    
                if (!jmx::recvMessage(serverFd, response)) {
                    return "ERROR: failed to receive response from server"; 
                } else {
                    responseJson = nlohmann::json::parse(response);
    
                    if (responseJson["status"] == "ERROR") {
                        return std::string("ERROR: ") + responseJson["message"].get<std::string>();
                    }
                }
            } catch (const std::exception& e) {
                return std::string("ERROR: Exception occurred while communicating with server: ") + e.what();
            }

        } 
        
        std::string error;
        if (!sessionManager.delete_session(error)) {
            return error;
        }
        
        std::string response_msg {};
        if (serverFd < 0) {
            response_msg = 
            "\n\n🟢🟢🟢🟢🟢🟢 SUCCESS 🟢🟢🟢🟢🟢🟢🟢\n"
            "Could not connect to server, but local session ended successfully.\n"
            "This may happen if the server is down or if the exam has already ended.\n"
            "If you submitted your answers, they should still be retained on the server.\n"
            "This is not an error message. Thank your using JMX.\n";
        } else {
            response_msg = 
            "\n\n🟢🟢🟢🟢🟢🟢 SUCCESS 🟢🟢🟢🟢🟢🟢🟢\n"
            "Ended session successfully. Thank your for using JMX.\n\n";
        }
        
        
        serverFd = {}; // Reset the server file descriptor

        return response_msg;
    }

    inline std::string handleGetQuestions() {
        SessionManager sessionManager;
        if (!sessionManager.check_session_exists()) {
            return "ERROR: No active session to fetch questions";
        }

        int serverFd = server::connectToServer();

        if (serverFd < 0) {
            return "ERROR: Failed to connect to server";
        }

        nlohmann::json message = {
            {"action", "get_questions"}
        };
        
        std::string response {};
        nlohmann::json responseJson;

        try {
            jmx::sendMessage(serverFd, message.dump());
    
            if (!jmx::recvMessage(serverFd, response)) {
                return "ERROR: failed to receive response from server"; 
            } else {
                responseJson = nlohmann::json::parse(response);
    
                if (responseJson["status"] == "ERROR") {
                    return std::string("ERROR: ") + responseJson["message"].get<std::string>();
                }
            }
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while fetching questions: ") + e.what();
        }

        try {
            std::string write_error;
            if (!writeQuestionFiles(responseJson["payload"].value("questions", nlohmann::json::array()), write_error)) {
                return "ERROR: " + write_error;
            }
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while writing questions to exam workspace: ") + e.what();
        }

        return "Successfully fetched questions and saved to exam workspace.";
    }

    inline std::string handleGetSubmissions(const nlohmann::json& request, bool best_only) {
        DaemonSettings settings;
        SessionManager sessionManager;
        if (!sessionManager.check_session_exists()) {
            return "ERROR: No active session to fetch submissions";
        }

        std::string qid;
        try {
            qid = request.at("payload").at("qid").get<std::string>();
        } catch (const std::exception&) {
            return "ERROR: Missing question ID";
        }

        if (qid.empty()) {
            return "ERROR: Missing question ID";
        }

        int serverFd = server::connectToServer();
        if (serverFd < 0) {
            return "ERROR: Failed to connect to server";
        }

        nlohmann::json message = {
            {"action", best_only ? "get_best_submission" : "get_recent_submissions"},
            {"payload", {
                {"qid", qid},
                {"student_id", sessionManager.get_student_id()}
            }}
        };

        std::string response {};
        nlohmann::json responseJson;

        try {
            jmx::sendMessage(serverFd, message.dump());

            if (!jmx::recvMessage(serverFd, response)) {
                return "ERROR: failed to receive response from server";
            }

            responseJson = nlohmann::json::parse(response);

            if (responseJson["status"] == "ERROR") {
                return std::string("ERROR: ") + responseJson["message"].get<std::string>();
            }
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while fetching submissions: ") + e.what();
        }

        std::string response_message = "Fetched submissions successfully.";
        if (responseJson.contains("message") && responseJson["message"].is_string()) {
            response_message = responseJson["message"].get<std::string>();
        }

        nlohmann::json submissions = nlohmann::json::array();
        try {
            const nlohmann::json& payload = responseJson.at("payload");
            if (payload.contains("submissions") && payload["submissions"].is_array()) {
                submissions = payload["submissions"];
            }
        } catch (const std::exception&) {
            return "ERROR: Malformed response from server";
        }

        const std::string folder_name = best_only ? "best-submissions" : "recent-submissions";
        const std::filesystem::path folder_path =
            std::filesystem::path(settings.workspace_directory) / folder_name;

        std::string folder_error;
        if (!exam_workspace_handler::reset_directory(folder_path, folder_error)) {
            return "ERROR: Could not prepare submission folder: " + folder_error;
        }

        if (submissions.empty()) {
            return response_message;
        }

        std::string saved_files;
        try {
            for (const auto& submission : submissions) {
                const std::string filename = submission["filename"].get<std::string>();
                const std::filesystem::path filename_path(filename);

                // The server supplies the filename. Keep it a plain file name
                // so a malformed response cannot write outside the folder.
                if (filename.empty() || filename_path.filename() != filename_path) {
                    return "ERROR: Server returned an invalid submission filename";
                }

                if (!exam_workspace_handler::write_file_to_directory(
                        folder_path,
                        filename,
                        submission["content"].get<std::string>())) {
                    return "ERROR: Failed to save submission to " + folder_path.string();
                }

                saved_files += "  - " + filename + "\n";
            }
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while saving submissions: ") + e.what();
        }

        std::string response_msg =
            response_message + "\n" +
            "Saved to: " + folder_path.string() + "\n" +
            saved_files;

        return response_msg;
    }

    inline std::string handleGetRecentSubmissions(const nlohmann::json& request) {
        return handleGetSubmissions(request, false);
    }

    inline std::string handleGetBestSubmission(const nlohmann::json& request) {
        return handleGetSubmissions(request, true);
    }

    inline std::string handleGetStats() {
        SessionManager sessionManager;
        if (!sessionManager.check_session_exists()) {
            return "ERROR: No active session to fetch stats";
        }

        int serverFd = server::connectToServer();

        if (serverFd < 0) {
            return "ERROR: Failed to connect to server";
        }

        nlohmann::json message = {
            {"action", "get_stats"},
            {"payload", {
                {"student_id", sessionManager.get_student_id()}
            }}
        };

        std::string stats_str;

        try {
            jmx::sendMessage(serverFd, message.dump());
            std::string response {};
            nlohmann::json responseJson;
    
            if (!jmx::recvMessage(serverFd, response)) {
                return "ERROR: failed to receive response from server"; 
            } else {
                responseJson = nlohmann::json::parse(response);
    
                if (responseJson["status"] == "ERROR") {
                    return std::string("ERROR: ") + responseJson["message"].get<std::string>();
                }
            }
    
            // Format the stats nicely
            stats_str = "\n🟢🟢🟢🟢🟢🟢 SUCCESS 🟢🟢🟢🟢🟢🟢🟢\n";
            stats_str += responseJson["message"].get<std::string>() + "\n";
            stats_str += responseJson["payload"]["stats"].get<std::string>() + "\n";
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while fetching stats: ") + e.what();
        }

        return stats_str;
    }

    inline std::string handleSubmit(nlohmann::json request) {
        DaemonSettings settings;
        SessionManager sessionManager;
        if (!sessionManager.check_session_exists()) {
            return "ERROR: No active session to submit solution";
        }

        char buffer[HOST_NAME_MAX + 1];
        std::string pc_id {};

        if (gethostname(buffer, sizeof(buffer)) == 0) {
            pc_id = std::string(buffer);
        } else {
            return "Error: Could not retrieve hostname";
        }

        // Read code from file
        std::string filename = request["payload"]["filename"].get<std::string>();
        std::filesystem::path file_path = std::filesystem::path(settings.workspace_directory) / filename;

        if (!std::filesystem::exists(file_path) || !std::filesystem::is_regular_file(file_path)) {
            return "Error: File does not exist in exam workspace: " + file_path.string();
        }

        std::ifstream file(file_path);
        if (!file.is_open()) {
            return "Error: Could not open file: " + file_path.string();
        }

        std::string code((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
        file.close();

        request["payload"]["student_id"] = sessionManager.get_student_id();
        request["payload"]["pc_id"] = pc_id;
        request["payload"]["code"] = code;

        int serverFd = server::connectToServer();

        if (serverFd < 0) {
            return "ERROR: Failed to connect to server";
        }

        std::string response {};
        nlohmann::json responseJson;
        
        try {
            jmx::sendMessage(serverFd, request.dump());
    
            if (!jmx::recvMessage(serverFd, response)) {
                return "ERROR: failed to receive response from server"; 
            } else {
                responseJson = nlohmann::json::parse(response);
    
                if (responseJson["status"] == "ERROR") {
                    return std::string("ERROR: ") + responseJson["message"].get<std::string>();
                }
            }
        } catch (const std::exception& e) {
            return std::string("ERROR: Exception occurred while submitting solution: ") + e.what();
        }

        // Portable string building: std::format needs GCC 13+, but the
        // release build targets Ubuntu 22.04 (GCC 11).
        std::string response_msg =
            "Solution submitted sucessfully for Question ID " +
            request["payload"]["qid"].get<std::string>() + ".\n Server response:\n" +
            "Verdict: " + responseJson["payload"]["verdict"].get<std::string>() + "\n" +
            "Score: " + std::to_string(responseJson["payload"]["score"].get<int>()) + "\n" +
            "Details: " + responseJson["payload"]["details"].get<std::string>() + "\n";

        return response_msg;
    }
}
