#pragma once

#include "../utils/connectToServer.hpp"
#include "../lib/json.hpp"
#include "../session/sessionManager.hpp"

#include <string>
#include <unistd.h>
#include <climits>

namespace command_handler {
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

            // Send a simple ping message to the server
            jmx::sendMessage(serverFd, request.dump());


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

            return responseJson["message"].get<std::string>();
        }
        
        return "Hi!";
    }

    inline std::string handleStart(const nlohmann::json& payload) {
        int serverFd = server::connectToServer();

        if (serverFd < 0) {
            return "ERROR: Failed to connect to server";
        }
        
        std::string payloadStr = payload.dump();
        
        jmx::sendMessage(serverFd, payloadStr);
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

        // Create session for student
        SessionManager sessionManager;
        std::string error;

        if (!sessionManager.create_session(
            error,
            responseJson["payload"]["student_id"],
            responseJson["payload"]["student_name"],
            responseJson["payload"]["exam_id"]
        )) {
            return error;
        }

        exam_workspace_handler::clear_directory();
        
        // For each question in responseJson["payload"]["questions"], write to a file in the exam_workspace directory
        for (const auto& question : responseJson["payload"]["questions"]) {
            std::string question_filename = question["qid"].get<std::string>() + question["extension"].get<std::string>();

            exam_workspace_handler::write_file_to_directory(
                std::filesystem::path(DaemonSettings().workspace_directory + "/" + question["qid"].get<std::string>()),
                question_filename,
                question["content"].get<std::string>()
            );
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

        // Write questions to exam_workspace
        for (const auto& question : responseJson["payload"]["questions"]) {
            std::string question_filename = question["qid"].get<std::string>() + question["extension"].get<std::string>();

            exam_workspace_handler::write_file_to_directory(
                std::filesystem::path(DaemonSettings().workspace_directory + "/" + question["qid"].get<std::string>()),
                question_filename,
                question["content"].get<std::string>()
            );
        }

        return "Successfully fetched questions and saved to exam workspace.";
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

        if (!std::filesystem::exists(file_path)) {
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

        jmx::sendMessage(serverFd, request.dump());
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

        std::string response_msg = std::format(
            "Solution submitted sucessfully for Question ID {}.\n Server response:\n"
            "Verdict: {}\n"
            "Score: {}\n"
            "Details: {}\n",
            request["payload"]["qid"].get<std::string>(),
            responseJson["payload"]["verdict"].get<std::string>(),
            responseJson["payload"]["score"].get<int>(),
            responseJson["payload"]["details"].get<std::string>()
        );

        return response_msg;
    }
}
