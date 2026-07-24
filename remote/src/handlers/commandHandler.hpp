#pragma once

#include "../headers/connectToServer.hpp"
#include "../lib/json.hpp"
#include "../session/sessionManager.hpp"

#include <string>

namespace command_handler {
    inline std::string handleHello() {
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
            "\n\n🟢🟢🟢🟢🟢🟢 SUCCESS 🟢🟢🟢🟢🟢🟢🟢\n\n"
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

        if (serverFd < 0) {
            return "ERROR: Failed to connect to server";
        }

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

        std::string error;
        if (!sessionManager.delete_session(error)) {
            return error;
        }

        serverFd = {}; // Reset the server file descriptor

        std::string response_msg = 
            "\n\n🟢🟢🟢🟢🟢🟢 SUCCESS 🟢🟢🟢🟢🟢🟢🟢\n\n"
            "Ended session successfully.\n\n";

        return response_msg;
    }
}
