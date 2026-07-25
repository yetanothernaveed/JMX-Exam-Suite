#pragma once

#include "Command.hpp"
#include <string>

class SubmitCommand : public Command {
private:
    CLI::App* sub_cmd_{nullptr};
    std::string filename{};
    std::string question_id{};
    std::string server_ip{};

public:
    void setup(CLI::App& app) override {
        sub_cmd_ = app.add_subcommand("submit", "Submit solution to server for evaluation");
        sub_cmd_->add_option("-q, --question-id", question_id, "Question identifier")->required();
        sub_cmd_->add_option("-f, --filename", filename, "Filename of the solution to submit. E.g. A.java")->required();
    }

    bool is_called() const override {
        return sub_cmd_ && *sub_cmd_;
    }

    nlohmann::json serialize() const override {
        return {
            {"action", "submit"},
            {"payload", {
                {"filename", filename},
                {"qid", question_id}
            }}
        };
    }
};
