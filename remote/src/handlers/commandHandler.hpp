#pragma once

#include "../utils/base64.hpp"
#include "../utils/connectToServer.hpp"
#include "../lib/json.hpp"
#include "../session/sessionManager.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <cstdint>
#include <string>
#include <string_view>
#include <unistd.h>
#include <climits>
#include <unordered_set>
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
    // A filename prefixed with "writable_" is written without the prefix and
    // with kiosk write permission; every other file stays read-only.
    // Text questions keep their original content; assets marked with
    // "encoding": "base64" are decoded and written as binary files.
    inline bool writeQuestionFiles(const nlohmann::json& questions,
                                   const fs::path& workspace,
                                   std::string& error,
                                   uid_t privileged_uid = 0,
                                   gid_t privileged_gid = 0) {
        exam_workspace_handler::UniqueFd workspace_fd;
        uid_t kiosk_uid{};
        gid_t kiosk_gid{};
        if (!exam_workspace_handler::open_workspace_directory(
                workspace, workspace_fd, kiosk_uid, kiosk_gid, error)) {
            return false;
        }

        std::unordered_set<std::string> destinations;

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

            std::string raw_filename = question.value("filename", std::string{});
            if (raw_filename.empty()) {
                raw_filename = qid + extension;
            }

            std::string filename;
            bool writable = false;
            if (!exam_workspace_handler::resolve_question_filename(
                    raw_filename, filename, writable, error)) {
                error = "Server returned an invalid filename for question '" + qid +
                        "': " + error;
                return false;
            }

            std::string final_extension = fs::path(filename).extension().string();
            std::transform(final_extension.begin(), final_extension.end(),
                           final_extension.begin(),
                           [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            if (final_extension != extension) {
                error = "Server returned a filename whose extension does not match the payload for question '" +
                        qid + "'";
                return false;
            }

            const std::string destination = qid + "/" + filename;
            if (!destinations.insert(destination).second) {
                error = "Server returned duplicate question file '" + destination + "'";
                return false;
            }

            const std::string encoding = question.value("encoding", std::string{"text"});
            // get_ref avoids a second copy of a potentially large base64 string.
            const std::string& content = question.at("content").get_ref<const std::string&>();

            std::vector<std::uint8_t> bytes;
            if (encoding == "base64") {
                std::string decode_error;
                if (!jmx::base64::decode(content, bytes, decode_error, jmx::kMaxMessageSize)) {
                    error = "Failed to decode question asset '" + filename + "': " + decode_error;
                    return false;
                }
            } else if (encoding != "text" && encoding != "utf-8") {
                error = "Unsupported encoding '" + encoding + "' for question '" + qid + "'";
                return false;
            }

            exam_workspace_handler::UniqueFd directory_fd;
            if (!exam_workspace_handler::ensure_question_directory(
                    workspace_fd.get(), qid, privileged_uid, privileged_gid,
                    directory_fd, error)) {
                return false;
            }

            const char* data = encoding == "base64"
                ? reinterpret_cast<const char*>(bytes.data())
                : content.data();
            const std::size_t size = encoding == "base64" ? bytes.size() : content.size();

            if (!exam_workspace_handler::write_question_file(
                    directory_fd.get(), filename, data, size, writable,
                    kiosk_uid, kiosk_gid, privileged_uid, privileged_gid, error)) {
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
            if (!writeQuestionFiles(responseJson["payload"].value("questions", nlohmann::json::array()),
                              fs::path(DaemonSettings().workspace_directory), write_error)) {
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
            if (!writeQuestionFiles(responseJson["payload"].value("questions", nlohmann::json::array()),
                              fs::path(DaemonSettings().workspace_directory), write_error)) {
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

        std::string qid;
        try {
            qid = request.at("payload").at("qid").get<std::string>();
        } catch (const std::exception&) {
            return "ERROR: Missing question ID";
        }
        if (!exam_workspace_handler::is_safe_path_component(qid)) {
            return "ERROR: Invalid question ID";
        }

        std::string requested_path;
        try {
            requested_path = request.at("payload").at("filename").get<std::string>();
        } catch (const std::exception&) {
            return "ERROR: Missing submission filename";
        }

        // Read the file from inside the exam workspace. Relative paths with
        // '/' are allowed, but no path component may be a symlink or '..'.
        exam_workspace_handler::UniqueFd workspace_fd;
        uid_t workspace_uid{};
        gid_t workspace_gid{};
        std::string path_error;
        if (!exam_workspace_handler::open_workspace_directory(
                settings.workspace_directory, workspace_fd,
                workspace_uid, workspace_gid, path_error)) {
            return "ERROR: " + path_error;
        }

        exam_workspace_handler::UniqueFd file_fd;
        std::string basename;
        if (!exam_workspace_handler::open_workspace_relative(
                workspace_fd.get(), requested_path, file_fd, basename, path_error)) {
            return "ERROR: " + path_error;
        }

        std::string code;
        if (!exam_workspace_handler::read_file_descriptor(file_fd.get(), code, path_error)) {
            return "ERROR: " + path_error;
        }

        char buffer[HOST_NAME_MAX + 1];
        std::string pc_id {};

        if (gethostname(buffer, sizeof(buffer)) == 0) {
            pc_id = std::string(buffer);
        } else {
            return "Error: Could not retrieve hostname";
        }

        request["payload"]["student_id"] = sessionManager.get_student_id();
        request["payload"]["pc_id"] = pc_id;
        // The server only uses the filename to pick the wrapper language and
        // name the stored response. Sending the basename keeps workspace
        // layout out of the submission payload.
        request["payload"]["filename"] = basename;
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
