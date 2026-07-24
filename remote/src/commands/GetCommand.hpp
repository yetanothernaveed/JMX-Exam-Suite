#pragma once

#include "Command.hpp"
#include <string>

class GetCommand : public Command {
private:
    CLI::App* sub_cmd_{nullptr};
    CLI::App* questions_sub_cmd_{nullptr};
    CLI::App* stats_sub_cmd_{nullptr};
    std::string student_id{};
    std::string server_ip{};

public:
    void setup(CLI::App& app) override {
        sub_cmd_ = app.add_subcommand("get", "Fetch resources from server");
        // required subcommands for "get"
        sub_cmd_->require_subcommand(1);
        questions_sub_cmd_ = sub_cmd_->add_subcommand("questions", "Fetch questions from server");
        stats_sub_cmd_ = sub_cmd_->add_subcommand("stats", "Fetch statistics for current active session");
    }

    bool is_called() const override {
        return (sub_cmd_ && *sub_cmd_) || (questions_sub_cmd_ && *questions_sub_cmd_) || (stats_sub_cmd_ && *stats_sub_cmd_);
    }

    nlohmann::json serialize() const override {
        if (questions_sub_cmd_ && *questions_sub_cmd_) {
            return {
                {"action", "get_questions"},
                {"payload", {}}
            };
        } else if (stats_sub_cmd_ && *stats_sub_cmd_) {
            return {
                {"action", "get_stats"},
                {"payload", {}}
            };
        }

        return {
            {"action", "get"},
            {"payload", {}}
        };
    }
};
