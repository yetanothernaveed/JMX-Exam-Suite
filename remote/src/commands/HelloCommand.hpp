#pragma once

#include "Command.hpp"
#include <string>

class HelloCommand : public Command {
private:
    CLI::App* sub_cmd_{nullptr};

public:
    void setup(CLI::App& app) override {
        sub_cmd_ = app.add_subcommand("hello", "Say hello to the JMX Daemon");
    }

    bool is_called() const override {
        return sub_cmd_ && *sub_cmd_;
    }

    nlohmann::json serialize() const override {
        return {
            {"action", "hello"}
        };
    }
};
