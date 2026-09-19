#include <filesystem>
#include <iostream>
#include <fcntl.h>
#include <sys/stat.h>
#include <ctime>
#include <chrono>
#include <string>

namespace fs = std::filesystem;

const fs::path TARGET_PATH = "/home/examkiosk/exam_workspace";
const fs::path SESSION_FILE_PATH = "/run/jmx/sessions/current_session.txt";
const fs::path BASE_ARCHIVE_DIR = "/var/tmp/jmxcleanerd";

// Creates the timestamped archive directory with 0700 permissions
fs::path create_timestamped_archive_dir(std::error_code& ec) {
    std::time_t now = std::time(nullptr);
    std::tm nowTm = *std::localtime(&now);

    char timeBuf[32];
    // Format: DD-MM-YYYY HH:MM:SS
    std::strftime(timeBuf, sizeof(timeBuf), "%d-%m-%Y %H:%M:%S", &nowTm);

    fs::path archiveSubdir = BASE_ARCHIVE_DIR / timeBuf;

    fs::create_directories(archiveSubdir, ec);
    if (ec) return {};

    // Apply 0700 (rwx------) permissions matching StateDirectoryMode=0700
    fs::permissions(archiveSubdir, fs::perms::owner_all, fs::perm_options::replace, ec);
    if (ec) return {};

    return archiveSubdir;
}

std::uintmax_t move_to_archive(const fs::path& source, const fs::path& targetDir, std::error_code& ec) {
    fs::path dest = targetDir / source.filename();

    // Fast atomic move on the same filesystem
    fs::rename(source, dest, ec);
    if (!ec) {
        return 1;
    }

    // Fallback for cross-filesystem moves
    ec.clear();
    fs::copy(source, dest, fs::copy_options::recursive | fs::copy_options::overwrite_existing, ec);

    if (!ec) {
        return fs::remove_all(source, ec);
    }

    return 0;
}


// Returns creation time as time_t, or -1 on failure/unsupported
time_t getCreationTime(const fs::path& path) {
    struct statx fileInfo;
    if (statx(AT_FDCWD, path.c_str(), 0, STATX_BTIME, &fileInfo) == 0) {
        if (fileInfo.stx_mask & STATX_BTIME) {
            return fileInfo.stx_btime.tv_sec;
        }
    }
    return -1;
}

time_t computeCutoff() {
    time_t now = std::time(nullptr);
    std::tm nowTm = *std::localtime(&now);

    std::tm midnightTm = nowTm;
    midnightTm.tm_hour = 0;
    midnightTm.tm_min = 0;
    midnightTm.tm_sec = 0;

    int currentHour = nowTm.tm_hour;
    const int slotStarts[] = {8, 11, 14, 17, 20};
    int chosenHour = -1;

    for (int h : slotStarts) {
        if (currentHour >= h) {
            chosenHour = h;
        }
    }

    std::tm cutoffTm = nowTm;
    if (chosenHour == -1) {
        cutoffTm = midnightTm;
    } else {
        cutoffTm.tm_hour = chosenHour;
        cutoffTm.tm_min = 0;
        cutoffTm.tm_sec = 0;
    }

    return mktime(&cutoffTm);
}

int main() {
    if (!fs::exists(TARGET_PATH)) {
        std::cerr << "Path does not exist: " << TARGET_PATH << "\n";
        return 1;
    }

    time_t cutoff = computeCutoff();

    std::error_code ec;
    std::uintmax_t removedCount = 0;
    int skippedNoTime = 0;
    fs::path currentArchiveDir;

    for (const auto& entry : fs::directory_iterator(TARGET_PATH, ec)) {
        time_t created = getCreationTime(entry.path());

        if (created == -1) {
            std::cerr << "Could not determine creation time, skipping: "
                      << entry.path() << "\n";
            skippedNoTime++;
            continue;
        }

        if (created < cutoff) {
            // Lazily create the timestamped folder once on the first file to be archived
            if (currentArchiveDir.empty()) {
                currentArchiveDir = create_timestamped_archive_dir(ec);
                if (ec) {
                    std::cerr << "Failed to create timestamped archive directory: " 
                              << ec.message() << "\n";
                    break;
                }
            }

            std::uintmax_t n = move_to_archive(entry.path(), currentArchiveDir, ec);
            if (ec) {
                std::cerr << "Failed to archive " << entry.path() << ": " << ec.message() << "\n";
                ec.clear();
            } else {
                removedCount += n;
                std::cout << "Archived: " << entry.path() << " -> " << currentArchiveDir << "\n";
            }
        }
    }

    std::cout << "Done. Removed " << removedCount << " entries. "
              << skippedNoTime << " skipped (no creation time available).\n";

    // Reset the session file if it's stale relative to the current cutoff
    ec.clear();
    fs::create_directories(SESSION_FILE_PATH.parent_path(), ec);
    if (ec) {
        std::cerr << "Failed to create session directory: " << ec.message() << "\n";
        return 1;
    }

    if (fs::exists(SESSION_FILE_PATH, ec)) {
        auto ftime = fs::last_write_time(SESSION_FILE_PATH, ec);
        if (ec) {
            std::cerr << "Failed to read session file timestamp: " << ec.message() << "\n";
        } else {
            auto sysTime = std::chrono::file_clock::to_sys(ftime);
            time_t sessionModTime = std::chrono::system_clock::to_time_t(sysTime);

            if (sessionModTime < cutoff) {
                fs::remove(SESSION_FILE_PATH, ec);
                if (ec) {
                    std::cerr << "Failed to remove session file: " << ec.message() << "\n";
                } else {
                    std::cout << "Session file reset (stale).\n";
                }
            }
        }
    }

    return 0;
}
