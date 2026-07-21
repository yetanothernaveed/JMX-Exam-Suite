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

        // ToDo
        // Clear exam_workspace directory
        // Write to question files

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
        int serverFd = server::connectToServer();

        SessionManager sessionManager;
        if (!sessionManager.check_session_exists()) {
            return "ERROR: No active session to end";
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
