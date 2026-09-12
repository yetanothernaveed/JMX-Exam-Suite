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

    for (const auto& entry : fs::directory_iterator(TARGET_PATH, ec)) {
        time_t created = getCreationTime(entry.path());

        if (created == -1) {
            std::cerr << "Could not determine creation time, skipping: "
                      << entry.path() << "\n";
            skippedNoTime++;
            continue;
        }

        if (created < cutoff) {
            std::uintmax_t n = fs::remove_all(entry.path(), ec);
            if (ec) {
                std::cerr << "Failed to remove " << entry.path() << ": " << ec.message() << "\n";
                ec.clear();
            } else {
                removedCount += n;
                std::cout << "Removed: " << entry.path() << "\n";
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
