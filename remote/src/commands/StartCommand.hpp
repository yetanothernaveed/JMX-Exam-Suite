#pragma once

#include "Command.hpp"
#include <string>
#include <unistd.h>

class StartCommand : public Command {
private:
    CLI::App* sub_cmd_{nullptr};
    std::string student_id{};
    std::string server_ip{};
    std::string hostname{};

public:
    void setup(CLI::App& app) override {
        sub_cmd_ = app.add_subcommand("start", "Start exam session");
        sub_cmd_->add_option("-i,--id", student_id, "Student ID")->required();
        
        char buffer[HOST_NAME_MAX + 1];
        gethostname(buffer, sizeof(buffer));
        this->hostname = std::string(buffer);
    }

    bool is_called() const override {
        return sub_cmd_ && *sub_cmd_;
    }

    nlohmann::json serialize() const override {
        return {
            {"action", "start"},
            {"payload", {
                {"student_id", student_id},
                {"hostname", hostname}
            }}
        };
    }
};
