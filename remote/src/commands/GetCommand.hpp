#pragma once

#include "Command.hpp"
#include <string>

class GetCommand : public Command {
private:
    CLI::App* sub_cmd_{nullptr};
    CLI::App* questions_sub_cmd_{nullptr};
    CLI::App* stats_sub_cmd_{nullptr};
    CLI::App* recent_submissions_sub_cmd_{nullptr};
    CLI::App* best_submission_sub_cmd_{nullptr};
    std::string recent_question_id{};
    std::string best_question_id{};
    std::string student_id{};
    std::string server_ip{};

public:
    void setup(CLI::App& app) override {
        sub_cmd_ = app.add_subcommand("get", "Fetch resources from server");
        // required subcommands for "get"
        sub_cmd_->require_subcommand(1);
        questions_sub_cmd_ = sub_cmd_->add_subcommand("questions", "Fetch questions from server");
        stats_sub_cmd_ = sub_cmd_->add_subcommand("stats", "Fetch statistics for current active session");

        recent_submissions_sub_cmd_ = sub_cmd_->add_subcommand(
            "recent-submissions", "Fetch the 3 most recent submissions for a question");
        recent_submissions_sub_cmd_
            ->add_option("-q, --question-id", recent_question_id, "Question identifier")
            ->required();

        best_submission_sub_cmd_ = sub_cmd_->add_subcommand(
            "best-submission", "Fetch the most recent best submission for a question");
        best_submission_sub_cmd_
            ->add_option("-q, --question-id", best_question_id, "Question identifier")
            ->required();
    }

    bool is_called() const override {
        return (sub_cmd_ && *sub_cmd_) ||
               (questions_sub_cmd_ && *questions_sub_cmd_) ||
               (stats_sub_cmd_ && *stats_sub_cmd_) ||
               (recent_submissions_sub_cmd_ && *recent_submissions_sub_cmd_) ||
               (best_submission_sub_cmd_ && *best_submission_sub_cmd_);
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
        } else if (recent_submissions_sub_cmd_ && *recent_submissions_sub_cmd_) {
            return {
                {"action", "get_recent_submissions"},
                {"payload", {
                    {"qid", recent_question_id}
                }}
            };
        } else if (best_submission_sub_cmd_ && *best_submission_sub_cmd_) {
            return {
                {"action", "get_best_submission"},
                {"payload", {
                    {"qid", best_question_id}
                }}
            };
        }

        return {
            {"action", "get"},
            {"payload", {}}
        };
    }
};
