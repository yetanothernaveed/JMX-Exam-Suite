#pragma once

#include "Command.hpp"
#include <string>

class HelloCommand : public Command {
private:
    CLI::App* sub_cmd_{nullptr};
    bool server_flag_{false};

public:
    void setup(CLI::App& app) override {
        sub_cmd_ = app.add_subcommand("hello", "Say hello to the JMX Daemon");
        sub_cmd_->add_flag_function("--server", [this](bool server_flag) {
            if (server_flag) {
                server_flag_ = true;
            }
        }, "Ask the server for a greeting.");
    }

    bool is_called() const override {
        return sub_cmd_ && *sub_cmd_;
    }

    nlohmann::json serialize() const override {
        if (this->server_flag_) {
            return {
                {"action", "hello"},
                {"payload", {
                    {"server", true}
                }}
            };
        }
        return {
            {"action", "hello"},
            {"payload", {
                {"server", false}
            }}
        };
    }
};
