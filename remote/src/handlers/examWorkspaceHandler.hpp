#pragma once

#include "../config/daemonSettings.hpp"

#include <cerrno>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <string_view>
#include <system_error>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

namespace fs = std::filesystem;

namespace exam_workspace_handler {
    // A file whose name starts with this prefix is delivered to the kiosk
    // without the prefix and is made writable by the kiosk user. Every other
    // delivered file stays read-only. The prefix is intentional and
    // case-sensitive so ordinary filenames cannot trigger it by accident.
    constexpr std::string_view kWritablePrefix = "writable_";

    // Bounds for `jmx submit -f`, which now accepts relative paths with '/'.
    constexpr std::size_t kMaxSubmitPathComponents = 16;
    constexpr std::size_t kMaxSubmitPathLength = 4096;

    struct UniqueFd {
        int fd{-1};

        UniqueFd() = default;
        explicit UniqueFd(int value) : fd(value) {}

        ~UniqueFd() { reset(); }

        UniqueFd(const UniqueFd&) = delete;
        UniqueFd& operator=(const UniqueFd&) = delete;

        void reset(int value = -1) {
            if (fd >= 0) {
                ::close(fd);
            }
            fd = value;
        }

        int get() const { return fd; }
    };

    // Server-supplied names are used to build paths inside the exam workspace.
    // Reject separators, parent references and embedded NULs so a malformed
    // response cannot write outside the workspace.
    inline bool is_safe_path_component(const std::string& name) {
        return !name.empty() && name != "." && name != ".." &&
               name.find('/') == std::string::npos &&
               name.find('\\') == std::string::npos &&
               name.find('\0') == std::string::npos;
    }

    // Strip the author's `writable_` marker. The marker never reaches the
    // student: `writable_q110.py` is written as `q110.py`.
    inline bool resolve_question_filename(const std::string& raw_name,
                                          std::string& final_name,
                                          bool& writable,
                                          std::string& error) {
        writable = false;
        std::string name = raw_name;

        if (name.rfind(kWritablePrefix, 0) == 0) {
            writable = true;
            name.erase(0, kWritablePrefix.size());
        }

        if (!is_safe_path_component(name) || fs::path(name).filename() != name) {
            error = "Invalid question filename '" + raw_name + "'";
            return false;
        }

        final_name = name;
        return true;
    }

    // Open the workspace itself with O_NOFOLLOW: the kiosk user owns the
    // workspace directory, so a symlink swap must not redirect daemon writes.
    // The directory owner is the kiosk user that should own writable files.
    inline bool open_workspace_directory(const fs::path& workspace,
                                         UniqueFd& out_fd,
                                         uid_t& owner_uid,
                                         gid_t& owner_gid,
                                         std::string& error) {
        int fd = ::open(workspace.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0) {
            error = "Could not open exam workspace '" + workspace.string() +
                    "': " + std::strerror(errno);
            return false;
        }

        struct stat st{};
        if (::fstat(fd, &st) != 0 || !S_ISDIR(st.st_mode)) {
            error = "Exam workspace '" + workspace.string() + "' is not a directory";
            ::close(fd);
            return false;
        }

        out_fd.reset(fd);
        owner_uid = st.st_uid;
        owner_gid = st.st_gid;
        return true;
    }

    // Create/reuse a qid directory and force it back to privileged ownership.
    // Students may edit individual writable files, but may not add, delete,
    // rename, or replace question files.
    inline bool ensure_question_directory(int workspace_fd,
                                          const std::string& qid,
                                          uid_t privileged_uid,
                                          gid_t privileged_gid,
                                          UniqueFd& out_fd,
                                          std::string& error) {
        if (!is_safe_path_component(qid)) {
            error = "Invalid question ID '" + qid + "'";
            return false;
        }

        if (::mkdirat(workspace_fd, qid.c_str(), 0755) != 0 && errno != EEXIST) {
            error = "Could not create question directory '" + qid +
                    "': " + std::strerror(errno);
            return false;
        }

        int fd = ::openat(workspace_fd, qid.c_str(),
                          O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0) {
            error = "Could not open question directory '" + qid +
                    "': " + std::strerror(errno);
            return false;
        }

        if (::fchown(fd, privileged_uid, privileged_gid) != 0 ||
            ::fchmod(fd, 0755) != 0) {
            error = "Could not secure question directory '" + qid +
                    "': " + std::strerror(errno);
            ::close(fd);
            return false;
        }

        out_fd.reset(fd);
        return true;
    }

    // Write a delivered question file and set its final ownership/mode before
    // the student can open it. O_NOFOLLOW prevents an existing symlink from
    // redirecting either the write or the metadata change.
    inline bool write_question_file(int directory_fd,
                                    const std::string& filename,
                                    const char* data,
                                    std::size_t size,
                                    bool writable,
                                    uid_t writable_uid,
                                    gid_t writable_gid,
                                    uid_t privileged_uid,
                                    gid_t privileged_gid,
                                    std::string& error) {
        if (!is_safe_path_component(filename) ||
            fs::path(filename).filename() != filename) {
            error = "Invalid question filename '" + filename + "'";
            return false;
        }

        int fd = ::openat(directory_fd, filename.c_str(),
                          O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC,
                          0600);
        if (fd < 0) {
            error = "Could not create question file '" + filename +
                    "': " + std::strerror(errno);
            return false;
        }

        std::size_t offset = 0;
        while (offset < size) {
            ssize_t written = ::write(fd, data + offset, size - offset);
            if (written < 0) {
                if (errno == EINTR) {
                    continue;
                }
                error = "Could not write question file '" + filename +
                        "': " + std::strerror(errno);
                ::close(fd);
                return false;
            }
            if (written == 0) {
                error = "Could not write question file '" + filename +
                        "': short write";
                ::close(fd);
                return false;
            }
            offset += static_cast<std::size_t>(written);
        }

        const uid_t owner_uid = writable ? writable_uid : privileged_uid;
        const gid_t owner_gid = writable ? writable_gid : privileged_gid;
        const mode_t mode = writable ? 0644 : 0444;

        if (::fchown(fd, owner_uid, owner_gid) != 0 || ::fchmod(fd, mode) != 0) {
            error = "Could not set permissions on question file '" + filename +
                    "': " + std::strerror(errno);
            ::close(fd);
            return false;
        }

        if (::close(fd) != 0) {
            error = "Could not close question file '" + filename +
                    "': " + std::strerror(errno);
            return false;
        }

        return true;
    }

    // Open a file for `jmx submit -f`. The path must be relative to the exam
    // workspace and every component is opened without following symlinks.
    inline bool open_workspace_relative(int workspace_fd,
                                        const std::string& relative_path,
                                        UniqueFd& out_fd,
                                        std::string& basename,
                                        std::string& error) {
        if (relative_path.empty() || relative_path.back() == '/') {
            error = "Submission filename must be a relative file path";
            return false;
        }
        if (relative_path.size() > kMaxSubmitPathLength ||
            relative_path.find('\0') != std::string::npos) {
            error = "Submission filename is too long or invalid";
            return false;
        }

        const fs::path path(relative_path);
        if (path.is_absolute()) {
            error = "Submission filename must be relative to the exam workspace";
            return false;
        }

        std::vector<std::string> parts;
        for (const auto& component : path) {
            const std::string part = component.string();
            if (part.empty() || part == "." || part == ".." ||
                part.find('/') != std::string::npos ||
                part.find('\\') != std::string::npos ||
                part.find('\0') != std::string::npos) {
                error = "Submission filename contains an invalid path component";
                return false;
            }
            parts.push_back(part);
        }

        if (parts.empty() || parts.size() > kMaxSubmitPathComponents) {
            error = "Submission filename has too many path components";
            return false;
        }

        UniqueFd cursor(::dup(workspace_fd));
        if (cursor.get() < 0) {
            error = "Could not inspect exam workspace: " + std::string(std::strerror(errno));
            return false;
        }

        for (std::size_t i = 0; i + 1 < parts.size(); ++i) {
            int next = ::openat(cursor.get(), parts[i].c_str(),
                                O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
            cursor.reset(next);
            if (next < 0) {
                error = "Submission path is not a real directory inside the exam workspace";
                return false;
            }
        }

        int fd = ::openat(cursor.get(), parts.back().c_str(),
                          O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
        if (fd < 0) {
            error = "Could not open submission file '" + relative_path +
                    "': " + std::strerror(errno);
            return false;
        }

        struct stat st{};
        if (::fstat(fd, &st) != 0 || !S_ISREG(st.st_mode)) {
            error = "Submission path is not a regular file";
            ::close(fd);
            return false;
        }

        basename = parts.back();
        out_fd.reset(fd);
        return true;
    }

    inline bool read_file_descriptor(int fd, std::string& content, std::string& error) {
        char buffer[8192];
        while (true) {
            ssize_t count = ::read(fd, buffer, sizeof(buffer));
            if (count < 0) {
                if (errno == EINTR) {
                    continue;
                }
                error = std::string("Could not read submission file: ") + std::strerror(errno);
                return false;
            }
            if (count == 0) {
                return true;
            }
            content.append(buffer, static_cast<std::size_t>(count));
        }
    }

    inline bool ensure_directory(const fs::path& dir_path) {
        std::error_code ec;
        if (!fs::exists(dir_path, ec)) {
            if (ec) {
                std::cerr << "Failed to inspect directory: " << dir_path
                          << " | Reason: " << ec.message() << std::endl;
                return false;
            }

            fs::create_directories(dir_path, ec);
            if (ec) {
                std::cerr << "Failed to create directory: " << dir_path
                          << " | Reason: " << ec.message() << std::endl;
                return false;
            }
        }
        return true;
    }

    inline bool clear_directory() {
        DaemonSettings settings;
        fs::path dir_path = fs::path(settings.workspace_directory);
        std::error_code ec;

        if (!fs::exists(dir_path, ec) || !fs::is_directory(dir_path, ec)) {
            std::cerr << "Target path is not a valid directory: " << dir_path << std::endl;
            return false;
        }

        bool all_cleared = true;

        for (const auto& entry : fs::directory_iterator(dir_path, ec)) {
            if (ec) {
                std::cerr << "Error while reading directory entries: " << ec.message() << std::endl;
                return false;
            }

            std::error_code remove_ec;
            fs::remove_all(entry.path(), remove_ec);

            if (remove_ec) {
                std::cerr << "Failed to delete item: " << entry.path()
                          << "Reason: " << remove_ec.message() << std::endl;

                all_cleared = false;
            }
        }

        if (ec) {
            std::cerr << "Directory iteration ended unexpectedly: " << ec.message() << std::endl;
            return false;
        }

        return all_cleared;
    }

    // Create `dir_path` if needed, or remove everything inside it if it already
    // exists. Filesystem errors are reported through `error` instead of being
    // thrown so callers inside the daemon can fail gracefully.
    inline bool reset_directory(const fs::path& dir_path, std::string& error) {
        std::error_code ec;

        // symlink_status() avoids following a symlink and deleting the
        // contents of an unrelated target directory.
        fs::file_status status = fs::symlink_status(dir_path, ec);
        if (ec) {
            if (ec == std::errc::no_such_file_or_directory) {
                // status() reports a missing path as an error, unlike exists().
                ec.clear();
                status = fs::file_status(fs::file_type::not_found);
            } else {
                error = "Could not inspect '" + dir_path.string() + "': " + ec.message();
                return false;
            }
        }

        if (!fs::exists(status)) {
            fs::create_directories(dir_path, ec);
            if (ec) {
                error = "Could not create '" + dir_path.string() + "': " + ec.message();
                return false;
            }
            return true;
        }

        if (!fs::is_directory(status)) {
            error = "'" + dir_path.string() + "' exists but is not a directory";
            return false;
        }

        fs::directory_iterator entry_it(dir_path, ec);
        if (ec) {
            error = "Could not read '" + dir_path.string() + "': " + ec.message();
            return false;
        }

        const fs::directory_iterator end_it;
        while (entry_it != end_it) {
            fs::remove_all(entry_it->path(), ec);
            if (ec) {
                error = "Could not remove '" + entry_it->path().string() + "': " + ec.message();
                return false;
            }

            entry_it.increment(ec);
            if (ec) {
                error = "Could not continue reading '" + dir_path.string() + "': " + ec.message();
                return false;
            }
        }

        return true;
    }

    inline bool write_file_to_directory(const fs::path& dir_path, const std::string& filename, const std::string& content) {
        if (!is_safe_path_component(filename) || !ensure_directory(dir_path)) {
            return false;
        }

        const fs::path file_path = dir_path / filename;

        std::ofstream ofs(file_path, std::ios::out | std::ios::trunc);
        if (!ofs.is_open()) {
            std::cerr << "Failed to create file: " << file_path << std::endl;
            return false;
        }

        ofs << content;
        ofs.close();

        if (!ofs) {
            std::cerr << "Failed to write file: " << file_path << std::endl;
            return false;
        }

        return true;
    }

    // Binary-safe counterpart for PDFs and images. Text-mode ofstreams would
    // corrupt these files (notably on Windows-style line endings and NULs).
    inline bool write_binary_file_to_directory(const fs::path& dir_path,
                                               const std::string& filename,
                                               const std::vector<std::uint8_t>& content) {
        if (!is_safe_path_component(filename) || !ensure_directory(dir_path)) {
            return false;
        }

        const fs::path file_path = dir_path / filename;

        std::ofstream ofs(file_path, std::ios::out | std::ios::binary | std::ios::trunc);
        if (!ofs.is_open()) {
            std::cerr << "Failed to create file: " << file_path << std::endl;
            return false;
        }

        if (!content.empty()) {
            ofs.write(reinterpret_cast<const char*>(content.data()),
                      static_cast<std::streamsize>(content.size()));
        }
        ofs.close();

        if (!ofs) {
            std::cerr << "Failed to write file: " << file_path << std::endl;
            return false;
        }

        return true;
    }

} // namespace exam_workspace_handler
