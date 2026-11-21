#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <dirent.h>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <optional>
#include <pwd.h>
#include <signal.h>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>

namespace fs = std::filesystem;

const fs::path TARGET_PATH = "/home/examkiosk/exam_workspace";
const fs::path SESSION_FILE_PATH = "/run/jmx/sessions/current_session.txt";
const fs::path BASE_ARCHIVE_DIR = "/var/tmp/jmxcleanerd";
const fs::path STATE_DIR = "/var/lib/jmxcleanerd";
const fs::path MARKER_PATH = STATE_DIR / "last_handled_slot";
const fs::path KIOSK_HOME = "/home/examkiosk";

constexpr const char* KIOSK_USER = "examkiosk";

// A reset is only allowed during the first minute after a slot boundary.
// Anything later is treated as mid-slot and must not terminate the kiosk.
constexpr std::time_t RESET_WINDOW_SECONDS = 60;

enum class Mode {
    ArchiveOnly,
    SlotReset
};

struct ArchiveResult {
    std::uintmax_t removedCount = 0;
    int skippedNoTime = 0;
    bool ok = true;
};

struct KioskProcess {
    pid_t pid = -1;
    time_t startTime = 0;
    bool isExamSession = false;
};

std::string formatTime(time_t value) {
    std::tm tm = *std::localtime(&value);
    char buffer[32];
    if (std::strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", &tm) == 0) {
        return "?";
    }
    return buffer;
}

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

// Slot boundaries are 00:00, 08:00, 11:00, 14:00, 17:00 and 20:00.
// Midnight is deliberately treated as a regular boundary. DST handling is
// intentionally omitted; the kiosk schedule is defined in local wall time.
time_t computeSlotStart(time_t now) {
    std::tm nowTm = *std::localtime(&now);
    const int slotStarts[] = {0, 8, 11, 14, 17, 20};
    int chosenHour = 0;

    for (int hour : slotStarts) {
        if (nowTm.tm_hour >= hour) {
            chosenHour = hour;
        }
    }

    nowTm.tm_hour = chosenHour;
    nowTm.tm_min = 0;
    nowTm.tm_sec = 0;

    return mktime(&nowTm);
}

std::optional<time_t> readMarker() {
    std::ifstream marker(MARKER_PATH);
    if (!marker.is_open()) {
        return std::nullopt;
    }

    long long value = 0;
    if (!(marker >> value) || value < 0) {
        return std::nullopt;
    }

    return static_cast<time_t>(value);
}

bool writeMarker(time_t slotStart) {
    std::error_code ec;
    fs::create_directories(STATE_DIR, ec);
    if (ec) {
        std::cerr << "Failed to create state directory " << STATE_DIR
                  << ": " << ec.message() << "\n";
        return false;
    }

    fs::permissions(STATE_DIR, fs::perms::owner_all, fs::perm_options::replace, ec);
    ec.clear();

    fs::path tempPath = MARKER_PATH;
    tempPath += ".tmp";

    {
        std::ofstream marker(tempPath, std::ios::out | std::ios::trunc);
        if (!marker.is_open()) {
            std::cerr << "Failed to open marker file for writing: " << tempPath << "\n";
            return false;
        }

        marker << static_cast<long long>(slotStart) << "\n";
        if (!marker) {
            std::cerr << "Failed to write marker file: " << tempPath << "\n";
            return false;
        }
    }

    fs::permissions(tempPath,
                    fs::perms::owner_read | fs::perms::owner_write,
                    fs::perm_options::replace,
                    ec);
    ec.clear();

    fs::rename(tempPath, MARKER_PATH, ec);
    if (ec) {
        std::cerr << "Failed to update marker file " << MARKER_PATH
                  << ": " << ec.message() << "\n";
        std::error_code removeEc;
        fs::remove(tempPath, removeEc);
        return false;
    }

    std::cout << "Recorded handled slot " << formatTime(slotStart) << ".\n";
    return true;
}

std::optional<uid_t> getKioskUid() {
    struct passwd* pw = getpwnam(KIOSK_USER);
    if (!pw) {
        return std::nullopt;
    }
    return pw->pw_uid;
}

std::optional<time_t> readBootTime() {
    std::ifstream statFile("/proc/stat");
    if (!statFile.is_open()) {
        return std::nullopt;
    }

    std::string line;
    while (std::getline(statFile, line)) {
        if (line.rfind("btime ", 0) != 0) {
            continue;
        }

        std::istringstream value(line.substr(6));
        long long bootTime = 0;
        if (value >> bootTime) {
            return static_cast<time_t>(bootTime);
        }
    }

    return std::nullopt;
}

bool isPidName(const char* name) {
    if (!name || !*name) {
        return false;
    }

    for (const char* p = name; *p; ++p) {
        if (*p < '0' || *p > '9') {
            return false;
        }
    }

    return true;
}

std::vector<KioskProcess> getKioskProcesses(uid_t uid) {
    std::vector<KioskProcess> processes;

    std::optional<time_t> bootTime = readBootTime();
    long ticksPerSecond = sysconf(_SC_CLK_TCK);
    if (!bootTime || ticksPerSecond <= 0) {
        return processes;
    }

    DIR* procDir = opendir("/proc");
    if (!procDir) {
        return processes;
    }

    while (struct dirent* entry = readdir(procDir)) {
        if (!isPidName(entry->d_name)) {
            continue;
        }

        std::string processPath = std::string("/proc/") + entry->d_name;

        std::ifstream statusFile(processPath + "/status");
        if (!statusFile.is_open()) {
            continue;
        }

        uid_t realUid = static_cast<uid_t>(-1);
        std::string line;
        while (std::getline(statusFile, line)) {
            if (line.rfind("Uid:", 0) != 0) {
                continue;
            }

            std::istringstream value(line.substr(4));
            unsigned long parsedUid = 0;
            if (value >> parsedUid) {
                realUid = static_cast<uid_t>(parsedUid);
            }
            break;
        }

        if (realUid != uid) {
            continue;
        }

        std::ifstream statFile(processPath + "/stat");
        if (!statFile.is_open()) {
            continue;
        }

        std::string statLine;
        if (!std::getline(statFile, statLine)) {
            continue;
        }

        // The comm field (field 2) may contain spaces and parentheses, so
        // parse relative to the final ')' to find the remaining fields.
        std::size_t closeParen = statLine.rfind(')');
        if (closeParen == std::string::npos) {
            continue;
        }

        std::istringstream statStream(statLine.substr(closeParen + 1));
        std::string state;
        if (!(statStream >> state)) {
            continue;
        }

        // Zombies have no live session state and should not keep the reset
        // waiting for them to disappear.
        if (state == "Z") {
            continue;
        }

        // After the state field, field 22 (starttime) is 19 tokens away.
        unsigned long long startTicks = 0;
        bool parsedStart = true;
        for (int i = 0; i < 19; ++i) {
            if (!(statStream >> startTicks)) {
                parsedStart = false;
                break;
            }
        }
        if (!parsedStart) {
            continue;
        }

        KioskProcess process;
        process.pid = static_cast<pid_t>(std::strtol(entry->d_name, nullptr, 10));
        process.startTime = *bootTime + static_cast<time_t>(
            startTicks / static_cast<unsigned long long>(ticksPerSecond));

        std::ifstream commandLine(processPath + "/cmdline", std::ios::binary);
        std::string command(
            (std::istreambuf_iterator<char>(commandLine)),
            std::istreambuf_iterator<char>());
        process.isExamSession =
            command.find("exam-session.sh") != std::string::npos;

        processes.push_back(process);
    }

    closedir(procDir);
    return processes;
}

bool runCommand(const std::vector<std::string>& args) {
    if (args.empty()) {
        return false;
    }

    pid_t pid = fork();
    if (pid < 0) {
        std::cerr << "fork() failed: " << std::strerror(errno) << "\n";
        return false;
    }

    if (pid == 0) {
        std::vector<char*> argv;
        argv.reserve(args.size() + 1);
        for (const std::string& arg : args) {
            argv.push_back(const_cast<char*>(arg.c_str()));
        }
        argv.push_back(nullptr);

        execvp(argv[0], argv.data());
        _exit(127);
    }

    int status = 0;
    while (waitpid(pid, &status, 0) < 0) {
        if (errno == EINTR) {
            continue;
        }
        std::cerr << "waitpid() failed: " << std::strerror(errno) << "\n";
        return false;
    }

    return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}

// SDDM does not respawn its greeter after logind terminates a session:
// sddm-helper receives SIGHUP and exits with code 1, which SDDM treats as an
// authentication failure. Restarting the display manager recovers the greeter
// instead of leaving the kiosk on a black VT.
bool restartDisplayManager() {
    std::cout << "Restarting the display manager...\n";

    // display-manager.service is the distro-independent alias. Fall back to
    // the kiosk's SDDM unit when the alias is not installed.
    if (runCommand({"systemctl", "restart", "display-manager.service"})) {
        return true;
    }

    std::cerr << "display-manager.service restart failed; trying sddm.service.\n";
    if (runCommand({"systemctl", "restart", "sddm.service"})) {
        return true;
    }

    std::cerr << "Failed to restart the display manager; "
                 "the kiosk may remain on a black screen.\n";
    return false;
}

bool hasKioskProcessStartedBefore(uid_t uid, time_t boundary) {
    for (const KioskProcess& process : getKioskProcesses(uid)) {
        if (process.startTime < boundary) {
            return true;
        }
    }
    return false;
}

void killKioskProcesses(uid_t uid, time_t boundary, int signalNumber) {
    for (const KioskProcess& process : getKioskProcesses(uid)) {
        if (process.pid <= 0 || process.startTime >= boundary) {
            continue;
        }

        if (kill(process.pid, signalNumber) != 0 && errno != ESRCH) {
            std::cerr << "Failed to signal pid " << process.pid
                      << ": " << std::strerror(errno) << "\n";
        }
    }
}

bool waitForNoKioskProcessesStartedBefore(uid_t uid,
                                          time_t boundary,
                                          std::chrono::milliseconds timeout) {
    auto deadline = std::chrono::steady_clock::now() + timeout;

    while (true) {
        if (!hasKioskProcessStartedBefore(uid, boundary)) {
            return true;
        }

        if (std::chrono::steady_clock::now() >= deadline) {
            return false;
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
}

bool shutdownKioskSession(uid_t uid, time_t boundary) {
    if (!hasKioskProcessStartedBefore(uid, boundary)) {
        return true;
    }

    std::cout << "Shutting down firejail sandboxes for " << KIOSK_USER << "...\n";
    if (!runCommand({"firejail", std::string("--shutdown=") + KIOSK_USER})) {
        std::cerr << "firejail shutdown failed or firejail is not installed; continuing.\n";
    }

    std::cout << "Terminating " << KIOSK_USER << " login session...\n";
    if (!runCommand({"loginctl", "terminate-user", KIOSK_USER})) {
        std::cerr << "loginctl terminate-user failed; continuing with process cleanup.\n";
    }

    if (waitForNoKioskProcessesStartedBefore(uid, boundary, std::chrono::seconds(10))) {
        return true;
    }

    std::cerr << "Old kiosk processes still running; sending SIGTERM.\n";
    killKioskProcesses(uid, boundary, SIGTERM);
    if (waitForNoKioskProcessesStartedBefore(uid, boundary, std::chrono::seconds(2))) {
        return true;
    }

    std::cerr << "Old kiosk processes still running; sending SIGKILL.\n";
    killKioskProcesses(uid, boundary, SIGKILL);
    return waitForNoKioskProcessesStartedBefore(uid, boundary, std::chrono::seconds(2));
}

std::optional<time_t> getSessionFileMtime() {
    std::error_code ec;
    if (!fs::exists(SESSION_FILE_PATH, ec)) {
        return std::nullopt;
    }

    auto ftime = fs::last_write_time(SESSION_FILE_PATH, ec);
    if (ec) {
        std::cerr << "Failed to read session file timestamp: " << ec.message() << "\n";
        return std::nullopt;
    }

    auto sysTime = std::chrono::file_clock::to_sys(ftime);
    return std::chrono::system_clock::to_time_t(sysTime);
}

bool resetSessionFileIfStale(time_t cutoff) {
    std::error_code ec;
    fs::create_directories(SESSION_FILE_PATH.parent_path(), ec);
    if (ec) {
        std::cerr << "Failed to create session directory: " << ec.message() << "\n";
        return false;
    }

    if (!fs::exists(SESSION_FILE_PATH, ec)) {
        if (ec) {
            std::cerr << "Failed to check session file: " << ec.message() << "\n";
            return false;
        }
        return true;
    }

    auto ftime = fs::last_write_time(SESSION_FILE_PATH, ec);
    if (ec) {
        std::cerr << "Failed to read session file timestamp: " << ec.message() << "\n";
        return false;
    }

    auto sysTime = std::chrono::file_clock::to_sys(ftime);
    time_t sessionModTime = std::chrono::system_clock::to_time_t(sysTime);

    if (sessionModTime < cutoff) {
        fs::remove(SESSION_FILE_PATH, ec);
        if (ec) {
            std::cerr << "Failed to remove session file: " << ec.message() << "\n";
            return false;
        }
        std::cout << "Session file reset (stale).\n";
    }

    return true;
}

bool removeSessionFile() {
    std::error_code ec;
    fs::remove(SESSION_FILE_PATH, ec);
    if (ec) {
        std::cerr << "Failed to remove session file: " << ec.message() << "\n";
        return false;
    }
    return true;
}

// Keep this list in sync with the cleanup guard in exam-session.sh.
// The settings/keybindings files themselves are rebuilt from /etc/jmx/vscode
// on every login, so they are deliberately not cleared here.
bool clearVSCodeState() {
    const std::vector<fs::path> paths = {
        KIOSK_HOME / ".config/Code/User/workspaceStorage",
        KIOSK_HOME / ".config/Code/User/globalStorage",
        KIOSK_HOME / ".config/Code/User/History",
        KIOSK_HOME / ".config/Code/User/Backups",
        KIOSK_HOME / ".config/Code/Backups",
        KIOSK_HOME / ".config/Code/CachedData",
        KIOSK_HOME / ".config/Code/CachedExtensionVSIXs",
        KIOSK_HOME / ".config/Code/Code Cache",
        KIOSK_HOME / ".config/Code/GPUCache",
        KIOSK_HOME / ".config/Code/DawnGraphiteCache",
        KIOSK_HOME / ".config/Code/DawnWebGPUCache",
        KIOSK_HOME / ".config/Code/logs",
        KIOSK_HOME / ".config/Code/Crashpad",
        KIOSK_HOME / ".config/Code/Service Worker",
        KIOSK_HOME / ".config/Code/Local Storage",
        KIOSK_HOME / ".config/Code/Session Storage",
        KIOSK_HOME / ".config/Code/IndexedDB",
        KIOSK_HOME / ".config/Code/blob_storage",
        KIOSK_HOME / ".config/Code/Network Persistent State",
        KIOSK_HOME / ".bash_history"
    };

    bool allCleared = true;
    std::cout << "Clearing VS Code ephemeral state...\n";

    for (const fs::path& path : paths) {
        std::error_code ec;
        fs::remove_all(path, ec);
        if (ec) {
            std::cerr << "Failed to remove " << path << ": " << ec.message() << "\n";
            allCleared = false;
        }
    }

    return allCleared;
}

ArchiveResult archiveExpiredWorkspace(time_t cutoff) {
    ArchiveResult result;
    std::error_code ec;
    fs::path currentArchiveDir;

    for (const auto& entry : fs::directory_iterator(TARGET_PATH, ec)) {
        if (ec) {
            break;
        }

        time_t created = getCreationTime(entry.path());
        if (created == -1) {
            std::cerr << "Could not determine creation time, skipping: "
                      << entry.path() << "\n";
            result.skippedNoTime++;
            continue;
        }

        if (created >= cutoff) {
            continue;
        }

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
            result.removedCount += n;
            std::cout << "Archived: " << entry.path() << " -> " << currentArchiveDir << "\n";
        }
    }

    if (ec) {
        std::cerr << "Workspace archive error: " << ec.message() << "\n";
        result.ok = false;
        ec.clear();
    }

    std::cout << "Done. Archived/removed " << result.removedCount << " entries. "
              << result.skippedNoTime << " skipped (no creation time available).\n";

    return result;
}

void printUsage(const char* program) {
    std::cout << "Usage: " << program << " [--slot-reset|--archive-only]\n"
              << "  --slot-reset    Archive expired files and reset the kiosk, but only\n"
              << "                  during the first " << RESET_WINDOW_SECONDS
              << " seconds after a slot boundary.\n"
              << "  --archive-only  Archive expired files without touching the kiosk.\n"
              << "                  This is the default mode.\n";
}

int main(int argc, char** argv) {
    Mode mode = Mode::ArchiveOnly;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];

        if (arg == "--slot-reset") {
            mode = Mode::SlotReset;
        } else if (arg == "--archive-only") {
            mode = Mode::ArchiveOnly;
        } else if (arg == "--help" || arg == "-h") {
            printUsage(argv[0]);
            return 0;
        } else {
            std::cerr << "Unknown argument: " << arg << "\n";
            printUsage(argv[0]);
            return 2;
        }
    }

    if (!fs::exists(TARGET_PATH)) {
        std::cerr << "Path does not exist: " << TARGET_PATH << "\n";
        return 1;
    }

    time_t now = std::time(nullptr);
    time_t slotStart = computeSlotStart(now);

    if (mode == Mode::ArchiveOnly) {
        ArchiveResult archive = archiveExpiredWorkspace(slotStart);
        bool sessionOk = resetSessionFileIfStale(slotStart);
        return (archive.ok && sessionOk) ? 0 : 1;
    }

    // This guard is what makes a mid-slot reset impossible. If the timer is
    // delayed past the boundary, the slot is left alone until the next one.
    bool insideResetWindow = now >= slotStart &&
        (now - slotStart) <= RESET_WINDOW_SECONDS;

    if (!insideResetWindow) {
        std::cout << "Outside the " << RESET_WINDOW_SECONDS
                  << "s reset window for slot " << formatTime(slotStart)
                  << "; archiving only.\n";
        ArchiveResult archive = archiveExpiredWorkspace(slotStart);
        bool sessionOk = resetSessionFileIfStale(slotStart);
        bool markerOk = writeMarker(slotStart);
        return (archive.ok && sessionOk && markerOk) ? 0 : 1;
    }

    std::optional<time_t> marker = readMarker();
    if (marker && *marker == slotStart) {
        std::cout << "Slot " << formatTime(slotStart)
                  << " already handled; archiving only.\n";
        ArchiveResult archive = archiveExpiredWorkspace(slotStart);
        bool sessionOk = resetSessionFileIfStale(slotStart);
        return (archive.ok && sessionOk) ? 0 : 1;
    }

    std::optional<uid_t> kioskUid = getKioskUid();
    if (!kioskUid) {
        std::cerr << "User " << KIOSK_USER
                  << " does not exist; cannot reset the kiosk session.\n";
        archiveExpiredWorkspace(slotStart);
        resetSessionFileIfStale(slotStart);
        return 1;
    }

    std::vector<KioskProcess> processes = getKioskProcesses(*kioskUid);
    std::optional<time_t> earliestStart;
    std::optional<time_t> examSessionStart;

    for (const KioskProcess& process : processes) {
        if (!earliestStart || process.startTime < *earliestStart) {
            earliestStart = process.startTime;
        }
        if (process.isExamSession &&
            (!examSessionStart || process.startTime < *examSessionStart)) {
            examSessionStart = process.startTime;
        }
    }

    // Prefer the launch script's process as the identity of the current kiosk
    // session. This avoids treating a lingering per-user daemon from an old
    // session as if the whole kiosk were still active. Fall back to the oldest
    // examkiosk process if the launch script is not visible.
    std::optional<time_t> activeSessionStart =
        examSessionStart ? examSessionStart : earliestStart;

    std::optional<time_t> sessionMtime = getSessionFileMtime();
    bool currentSlotSession = sessionMtime && *sessionMtime >= slotStart;

    // A session that started at or after the boundary belongs to the new slot.
    // Killing it would be exactly the mid-slot reset that must never happen.
    if (activeSessionStart && *activeSessionStart >= slotStart) {
        std::cout << "Kiosk session started in the current slot; skipping reset.\n";
        ArchiveResult archive = archiveExpiredWorkspace(slotStart);
        bool sessionOk = resetSessionFileIfStale(slotStart);
        bool markerOk = writeMarker(slotStart);
        return (archive.ok && sessionOk && markerOk) ? 0 : 1;
    }

    // If there is no live process but a current-slot session file exists, the
    // student has started a session and we must not wipe it out from under them.
    if (!activeSessionStart && currentSlotSession) {
        std::cout << "Current-slot session file present; skipping reset.\n";
        ArchiveResult archive = archiveExpiredWorkspace(slotStart);
        bool sessionOk = resetSessionFileIfStale(slotStart);
        bool markerOk = writeMarker(slotStart);
        return (archive.ok && sessionOk && markerOk) ? 0 : 1;
    }

    if (activeSessionStart) {
        std::cout << "Resetting kiosk for slot " << formatTime(slotStart) << "...\n";
        if (!shutdownKioskSession(*kioskUid, slotStart)) {
            std::cerr << "Failed to terminate the kiosk session; marker not updated.\n";
            // The session may already be half torn down. Bring the display
            // manager back so the kiosk is not left on a black screen.
            restartDisplayManager();
            return 1;
        }

        // A display manager with autologin enabled may start the next session
        // while the old one is still shutting down. Never wipe state from under
        // a session that belongs to the new slot.
        bool newSessionAppeared = false;
        for (const KioskProcess& process : getKioskProcesses(*kioskUid)) {
            if (process.startTime >= slotStart) {
                newSessionAppeared = true;
                break;
            }
        }

        std::optional<time_t> latestSessionMtime = getSessionFileMtime();
        if (latestSessionMtime && *latestSessionMtime >= slotStart) {
            newSessionAppeared = true;
        }

        if (newSessionAppeared) {
            std::cout << "A new-slot session appeared during shutdown; "
                         "skipping state wipe.\n";
            ArchiveResult archive = archiveExpiredWorkspace(slotStart);
            bool sessionOk = resetSessionFileIfStale(slotStart);
            bool markerOk = writeMarker(slotStart);
            return (archive.ok && sessionOk && markerOk) ? 0 : 1;
        }
    } else {
        std::cout << "No active kiosk session; clearing idle state.\n";
    }

    ArchiveResult archive = archiveExpiredWorkspace(slotStart);
    bool sessionOk = removeSessionFile();
    bool stateOk = clearVSCodeState();

    bool markerOk = false;
    if (archive.ok && sessionOk && stateOk) {
        markerOk = writeMarker(slotStart);
    }

    // SDDM leaves a black VT after logind terminates a session. Restart the
    // display manager so the next student gets a login screen even when the
    // cleanup above partially failed.
    bool displayOk = true;
    if (activeSessionStart) {
        displayOk = restartDisplayManager();
    }

    if (!archive.ok) {
        std::cerr << "Workspace archive failed; marker not updated.\n";
    }
    if (!sessionOk) {
        std::cerr << "Failed to remove the session file; marker not updated.\n";
    }
    if (!stateOk) {
        std::cerr << "Failed to clear all VS Code state; marker not updated.\n";
    }
    if (!markerOk && archive.ok && sessionOk && stateOk) {
        std::cerr << "Failed to record the handled slot; a later run will retry.\n";
    }

    if (!archive.ok || !sessionOk || !stateOk || !markerOk || !displayOk) {
        return 1;
    }

    std::cout << "Slot reset complete for " << formatTime(slotStart) << ".\n";
    return 0;
}
