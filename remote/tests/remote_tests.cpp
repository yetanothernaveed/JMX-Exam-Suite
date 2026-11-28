#include "../src/handlers/commandHandler.hpp"

#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

namespace fs = std::filesystem;

namespace {

int failures = 0;

void check(bool condition, const std::string& name) {
    if (condition) {
        std::cout << "ok - " << name << '\n';
    } else {
        std::cerr << "FAIL - " << name << '\n';
        ++failures;
    }
}

fs::path make_workspace(const std::string& label) {
    const fs::path path = fs::temp_directory_path() /
                          ("jmx-remote-tests-" + std::to_string(::getpid()) + "-" + label);
    fs::remove_all(path);
    fs::create_directories(path);

    // Make the temp workspace look like the kiosk workspace: owned by a
    // non-root user. On an unprivileged test run it is already owned by the
    // current user, which is all the mode checks need.
    if (::geteuid() == 0 && ::chown(path.c_str(), 65534, 65534) != 0) {
        std::cerr << "WARNING: could not chown test workspace to nobody\n";
    }
    return path;
}

mode_t mode_of(const fs::path& path) {
    struct stat st{};
    if (::stat(path.c_str(), &st) != 0) {
        return 0;
    }
    return static_cast<mode_t>(st.st_mode & 07777);
}

uid_t uid_of(const fs::path& path) {
    struct stat st{};
    if (::stat(path.c_str(), &st) != 0) {
        return static_cast<uid_t>(-1);
    }
    return st.st_uid;
}

void test_resolve_filename() {
    std::string name;
    bool writable = false;
    std::string error;

    check(exam_workspace_handler::resolve_question_filename(
              "writable_q110.py", name, writable, error) &&
              name == "q110.py" && writable,
          "writable_ prefix is stripped and marked writable");

    name.clear();
    writable = false;
    check(exam_workspace_handler::resolve_question_filename(
              "Q110.md", name, writable, error) &&
              name == "Q110.md" && !writable,
          "ordinary filename is unchanged and read-only");

    check(!exam_workspace_handler::resolve_question_filename(
              "writable_", name, writable, error),
          "empty writable suffix is rejected");

    check(!exam_workspace_handler::resolve_question_filename(
              "writable_a/b.py", name, writable, error),
          "prefixed filename with separator is rejected");

    check(!exam_workspace_handler::resolve_question_filename(
              "writable_..", name, writable, error),
          "prefixed parent reference is rejected");
}

void test_delivery_permissions() {
    const fs::path workspace = make_workspace("delivery");
    const uid_t privileged_uid = ::geteuid() == 0 ? 0 : ::getuid();
    const gid_t privileged_gid = ::geteuid() == 0 ? 0 : ::getgid();

    nlohmann::json questions = nlohmann::json::array();
    questions.push_back({
        {"qid", "Q110"},
        {"filename", "writable_q110.py"},
        {"extension", ".py"},
        {"encoding", "text"},
        {"content", "print('hello')\n"}
    });
    questions.push_back({
        {"qid", "Q110"},
        {"filename", "Q110.md"},
        {"extension", ".md"},
        {"encoding", "text"},
        {"content", "# Question\n"}
    });
    questions.push_back({
        {"qid", "Q110"},
        {"filename", "Resume.pdf"},
        {"extension", ".pdf"},
        {"encoding", "base64"},
        {"content", "JVBERg=="}
    });

    std::string error;
    const bool written = command_handler::writeQuestionFiles(
        questions, workspace, error, privileged_uid, privileged_gid);
    check(written, "mixed question package is written: " + error);

    const fs::path question_dir = workspace / "Q110";
    const fs::path writable_file = question_dir / "q110.py";
    const fs::path read_only_text = question_dir / "Q110.md";
    const fs::path read_only_asset = question_dir / "Resume.pdf";

    check(fs::exists(writable_file), "writable_ prefix is not visible to student");
    check(!fs::exists(question_dir / "writable_q110.py"), "prefixed source name is not delivered");
    check(fs::exists(read_only_text), "ordinary text file is delivered unchanged");
    check(fs::exists(read_only_asset), "binary asset is delivered unchanged");

    check(mode_of(writable_file) == 0644, "writable file mode is 0644");
    check(mode_of(read_only_text) == 0444, "read-only text file mode is 0444");
    check(mode_of(read_only_asset) == 0444, "read-only asset mode is 0444");
    check(mode_of(question_dir) == 0755, "question directory mode is 0755");

    if (::geteuid() == 0) {
        check(uid_of(writable_file) == 65534, "writable file is owned by kiosk user");
        check(uid_of(read_only_text) == 0, "read-only file is owned by root");
        check(uid_of(question_dir) == 0, "question directory is owned by root");
    }

    std::string content;
    std::ifstream input(writable_file);
    std::getline(input, content);
    check(content == "print('hello')", "writable file content is unchanged");

    fs::remove_all(workspace);
}

void test_duplicate_destination() {
    const fs::path workspace = make_workspace("collision");
    const uid_t privileged_uid = ::geteuid() == 0 ? 0 : ::getuid();
    const gid_t privileged_gid = ::geteuid() == 0 ? 0 : ::getgid();

    nlohmann::json questions = nlohmann::json::array();
    questions.push_back({
        {"qid", "Q110"}, {"filename", "q110.py"}, {"extension", ".py"},
        {"encoding", "text"}, {"content", "a"}
    });
    questions.push_back({
        {"qid", "Q110"}, {"filename", "writable_q110.py"}, {"extension", ".py"},
        {"encoding", "text"}, {"content", "b"}
    });

    std::string error;
    check(!command_handler::writeQuestionFiles(
              questions, workspace, error, privileged_uid, privileged_gid),
          "colliding destination is rejected");
    check(error.find("duplicate") != std::string::npos,
          "collision error names the duplicate");

    fs::remove_all(workspace);
}

void test_submit_paths() {
    const fs::path workspace = make_workspace("submit");
    fs::create_directories(workspace / "Q110");
    {
        std::ofstream output(workspace / "Q110" / "q110.py");
        output << "answer\n";
    }
    fs::create_directory_symlink(fs::path("/etc"), workspace / "escape");

    exam_workspace_handler::UniqueFd workspace_fd;
    uid_t owner_uid{};
    gid_t owner_gid{};
    std::string error;
    check(exam_workspace_handler::open_workspace_directory(
              workspace, workspace_fd, owner_uid, owner_gid, error),
          "workspace opens without following symlinks: " + error);

    exam_workspace_handler::UniqueFd file_fd;
    std::string basename;
    check(exam_workspace_handler::open_workspace_relative(
              workspace_fd.get(), "Q110/q110.py", file_fd, basename, error) &&
              basename == "q110.py",
          "nested submit path is accepted");

    std::string code;
    check(exam_workspace_handler::read_file_descriptor(file_fd.get(), code, error) &&
              code == "answer\n",
          "nested submit file content is read");

    check(!exam_workspace_handler::open_workspace_relative(
              workspace_fd.get(), "../outside", file_fd, basename, error),
          "parent traversal is rejected");
    check(!exam_workspace_handler::open_workspace_relative(
              workspace_fd.get(), "/etc/passwd", file_fd, basename, error),
          "absolute path is rejected");
    check(!exam_workspace_handler::open_workspace_relative(
              workspace_fd.get(), "escape/passwd", file_fd, basename, error),
          "symlinked directory is rejected");
    check(!exam_workspace_handler::open_workspace_relative(
              workspace_fd.get(), "Q110", file_fd, basename, error),
          "directory is rejected as submission file");
    check(!exam_workspace_handler::open_workspace_relative(
              workspace_fd.get(), "Q110/missing.py", file_fd, basename, error),
          "missing nested file is rejected");

    fs::remove_all(workspace);
}

} // namespace

int main() {
    test_resolve_filename();
    test_delivery_permissions();
    test_duplicate_destination();
    test_submit_paths();

    if (failures == 0) {
        std::cout << "All remote tests passed.\n";
    }
    return failures == 0 ? 0 : 1;
}
