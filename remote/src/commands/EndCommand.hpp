#pragma once

#include "Command.hpp"
#include "../session/sessionManager.hpp"
#include <string>

class EndCommand : public Command {
private:
    CLI::App* sub_cmd_{nullptr};

public:
    void setup(CLI::App& app) override {
        sub_cmd_ = app.add_subcommand("end", "End the current session");
    }

    bool is_called() const override {
        return sub_cmd_ && *sub_cmd_;
    }

    nlohmann::json serialize() const override {
        SessionManager sessionManager;
        return {
            {"action", "end"}
        };
    }
};
