// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cctype>
#include <climits>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace D2Cleanup {

struct Request {
    std::string manifest;
    std::string cleanup_token;
    std::string cleanup_invocation_id;
    std::string run_id;
    std::string collection;
    std::string app_id;
    std::string database_path;
};

struct RuntimePaths {
    std::string proc_root = "/proc";
    std::string systemctl = "/usr/bin/systemctl";
    std::string sha256sum = "/usr/bin/sha256sum";
    std::string self_exe = "/proc/self/exe";
    std::string socket_path;
};

struct RuntimeIdentity {
    std::string executable_path;
    std::string executable_sha256;
    std::string service_unit;
    std::string invocation_id;
    pid_t service_main_pid = 0;
    pid_t engine_pid = 0;
    std::string database_path;
    std::string socket_path;
    std::string socket_inode;
};

inline bool IsHex(const std::string& value, std::size_t expected_size) {
    if (value.size() != expected_size) {
        return false;
    }
    for (const char ch : value) {
        const bool digit = ch >= '0' && ch <= '9';
        const bool lower = ch >= 'a' && ch <= 'f';
        const bool upper = ch >= 'A' && ch <= 'F';
        if (!digit && !lower && !upper) {
            return false;
        }
    }
    return true;
}

inline std::string CanonicalPath(const std::string& path) {
    char* resolved = ::realpath(path.c_str(), nullptr);
    if (resolved == nullptr) {
        throw std::runtime_error(
            "cannot resolve path: " + path + ": " + std::strerror(errno));
    }
    const std::string canonical(resolved);
    std::free(resolved);
    return canonical;
}

inline struct stat RequireCanonicalRegularFile(const std::string& path,
                                               const std::string& label) {
    if (path.empty() || path.front() != '/') {
        throw std::runtime_error(label + " must be an absolute path");
    }

    struct stat info {};
    if (::lstat(path.c_str(), &info) != 0) {
        throw std::runtime_error(
            label + " is missing or unreadable: " + std::strerror(errno));
    }
    if (S_ISLNK(info.st_mode)) {
        throw std::runtime_error(label + " must not be a symbolic link");
    }
    if (!S_ISREG(info.st_mode)) {
        throw std::runtime_error(label + " must be a regular file");
    }
    if (CanonicalPath(path) != path) {
        throw std::runtime_error(label + " path must already be canonical");
    }
    return info;
}

inline std::map<std::string, std::string> ReadManifest(
    const std::string& manifest_path) {
    const struct stat info =
        RequireCanonicalRegularFile(manifest_path, "cleanup manifest");
    if (info.st_uid != ::geteuid()) {
        throw std::runtime_error("cleanup manifest must be owned by the current user");
    }
    if ((info.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        throw std::runtime_error("cleanup manifest must not be group/world writable");
    }
    if (info.st_size <= 0 || info.st_size > 64 * 1024) {
        throw std::runtime_error("cleanup manifest size is outside the allowed range");
    }

    std::ifstream input(manifest_path);
    if (!input) {
        throw std::runtime_error("failed to open cleanup manifest");
    }

    std::map<std::string, std::string> values;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty() || line.find('\r') != std::string::npos) {
            throw std::runtime_error("cleanup manifest contains an invalid line");
        }
        const std::size_t separator = line.find('=');
        if (separator == std::string::npos || separator == 0) {
            throw std::runtime_error("cleanup manifest line is not key=value");
        }
        const std::string key = line.substr(0, separator);
        const std::string value = line.substr(separator + 1);
        for (const char ch : key) {
            const bool lower = ch >= 'a' && ch <= 'z';
            const bool digit = ch >= '0' && ch <= '9';
            if (!lower && !digit && ch != '_') {
                throw std::runtime_error("cleanup manifest contains an invalid key");
            }
        }
        if (!values.emplace(key, value).second) {
            throw std::runtime_error("cleanup manifest contains duplicate key: " + key);
        }
    }
    if (!input.eof()) {
        throw std::runtime_error("failed while reading cleanup manifest");
    }
    return values;
}

inline const std::string& RequireValue(
    const std::map<std::string, std::string>& values,
    const std::string& key) {
    const auto found = values.find(key);
    if (found == values.end()) {
        throw std::runtime_error("cleanup manifest is missing key: " + key);
    }
    return found->second;
}

inline void RequireEqual(const std::map<std::string, std::string>& values,
                         const std::string& key,
                         const std::string& expected) {
    if (RequireValue(values, key) != expected) {
        throw std::runtime_error("cleanup manifest mismatch for key: " + key);
    }
}

inline std::map<std::string, std::string> ValidateManifest(
    const Request& request) {
    if (!IsHex(request.cleanup_token, 64)) {
        throw std::runtime_error("--cleanup-token must be 64 hexadecimal characters");
    }
    if (!IsHex(request.cleanup_invocation_id, 32)) {
        throw std::runtime_error(
            "--cleanup-invocation-id must be 32 hexadecimal characters");
    }

    const std::string root_marker = "/d2-b-vector-smoke-" + request.run_id + "/";
    const std::size_t root_position = request.database_path.find(root_marker);
    if (root_position == std::string::npos) {
        throw std::runtime_error(
            "cleanup database is outside the run-specific D2 test root");
    }
    const std::string expected_manifest =
        request.database_path.substr(0, root_position + root_marker.size() - 1) +
        "/d2-vector-smoke.manifest";
    if (request.manifest != expected_manifest) {
        throw std::runtime_error(
            "cleanup manifest is not the fixed manifest for the current run_id");
    }

    const auto values = ReadManifest(request.manifest);
    RequireEqual(values, "format_version", "2");
    RequireEqual(values, "run_state", "cleanup_in_progress");
    RequireEqual(values, "run_id", request.run_id);
    RequireEqual(values, "collection", request.collection);
    RequireEqual(values, "app_id", request.app_id);
    RequireEqual(values, "database_path", request.database_path);
    RequireEqual(values, "created_by_prepare", "true");
    RequireEqual(values, "cleanup_completed", "false");
    RequireEqual(values, "collection_absent_verified", "false");
    RequireEqual(values, "cleanup_token", request.cleanup_token);
    RequireEqual(values, "cleanup_invocation_id", request.cleanup_invocation_id);

    const std::string& binary_hash = RequireValue(values, "binary_sha256");
    if (!IsHex(binary_hash, 64)) {
        throw std::runtime_error("cleanup manifest binary_sha256 is invalid");
    }
    RequireEqual(values, "cleanup_binary_sha256", binary_hash);

    const struct stat database =
        RequireCanonicalRegularFile(request.database_path, "cleanup database");
    RequireEqual(values, "database_device",
                 std::to_string(static_cast<unsigned long long>(database.st_dev)));
    RequireEqual(values, "database_inode",
                 std::to_string(static_cast<unsigned long long>(database.st_ino)));
    return values;
}

inline void Validate(const Request& request) {
    (void)ValidateManifest(request);
}

inline bool HexEqual(const std::string& left, const std::string& right) {
    if (left.size() != right.size()) {
        return false;
    }
    for (std::size_t index = 0; index < left.size(); ++index) {
        const unsigned char lhs = static_cast<unsigned char>(left[index]);
        const unsigned char rhs = static_cast<unsigned char>(right[index]);
        if (std::tolower(lhs) != std::tolower(rhs)) {
            return false;
        }
    }
    return true;
}

inline std::string CaptureCommand(const std::string& executable,
                                  const std::vector<std::string>& arguments) {
    if (executable.empty() || executable.front() != '/') {
        throw std::runtime_error("runtime identity command must be an absolute path");
    }
    const std::string canonical_executable = CanonicalPath(executable);
    struct stat executable_info {};
    if (::stat(canonical_executable.c_str(), &executable_info) != 0 ||
        !S_ISREG(executable_info.st_mode) ||
        ::access(canonical_executable.c_str(), X_OK) != 0) {
        throw std::runtime_error(
            "runtime identity command is not an executable regular file: " +
            canonical_executable);
    }

    std::vector<std::string> storage;
    storage.reserve(arguments.size() + 1);
    storage.push_back(canonical_executable);
    storage.insert(storage.end(), arguments.begin(), arguments.end());
    std::vector<char*> argv;
    argv.reserve(storage.size() + 1);
    for (std::string& value : storage) {
        argv.push_back(&value[0]);
    }
    argv.push_back(nullptr);

    int output_pipe[2] = {-1, -1};
    if (::pipe(output_pipe) != 0) {
        throw std::runtime_error(
            "failed to create runtime identity command pipe: " +
            std::string(std::strerror(errno)));
    }

    const pid_t child = ::fork();
    if (child < 0) {
        const int saved_errno = errno;
        ::close(output_pipe[0]);
        ::close(output_pipe[1]);
        throw std::runtime_error(
            "failed to fork runtime identity command: " +
            std::string(std::strerror(saved_errno)));
    }
    if (child == 0) {
        ::close(output_pipe[0]);
        if (::dup2(output_pipe[1], STDOUT_FILENO) < 0) {
            _exit(126);
        }
        ::close(output_pipe[1]);
        const int null_fd = ::open("/dev/null", O_WRONLY);
        if (null_fd >= 0) {
            (void)::dup2(null_fd, STDERR_FILENO);
            ::close(null_fd);
        }

        ::execv(canonical_executable.c_str(), argv.data());
        _exit(127);
    }

    ::close(output_pipe[1]);
    std::string output;
    bool output_too_large = false;
    char buffer[4096];
    while (true) {
        const ssize_t count = ::read(output_pipe[0], buffer, sizeof(buffer));
        if (count > 0) {
            if (output.size() + static_cast<std::size_t>(count) <= 64 * 1024) {
                output.append(buffer, static_cast<std::size_t>(count));
            } else {
                output_too_large = true;
            }
            continue;
        }
        if (count == 0) {
            break;
        }
        if (errno == EINTR) {
            continue;
        }
        const int saved_errno = errno;
        ::close(output_pipe[0]);
        int ignored_status = 0;
        (void)::waitpid(child, &ignored_status, 0);
        throw std::runtime_error(
            "failed to read runtime identity command output: " +
            std::string(std::strerror(saved_errno)));
    }
    ::close(output_pipe[0]);

    int status = 0;
    while (::waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) {
            throw std::runtime_error(
                "failed to wait for runtime identity command: " +
                std::string(std::strerror(errno)));
        }
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        throw std::runtime_error("runtime identity command failed: " + executable);
    }
    if (output_too_large) {
        throw std::runtime_error("runtime identity command output is too large");
    }
    return output;
}

inline std::map<std::string, std::string> ParseKeyValueOutput(
    const std::string& output,
    const std::string& label) {
    std::map<std::string, std::string> values;
    std::istringstream input(output);
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) {
            continue;
        }
        if (line.find('\r') != std::string::npos) {
            throw std::runtime_error(label + " contains a carriage return");
        }
        const std::size_t separator = line.find('=');
        if (separator == std::string::npos || separator == 0) {
            throw std::runtime_error(label + " contains a non key=value line");
        }
        const std::string key = line.substr(0, separator);
        if (!values.emplace(key, line.substr(separator + 1)).second) {
            throw std::runtime_error(label + " contains duplicate key: " + key);
        }
    }
    return values;
}

inline pid_t ParsePid(const std::string& value, const std::string& label) {
    if (value.empty()) {
        throw std::runtime_error(label + " is empty");
    }
    char* end = nullptr;
    errno = 0;
    const long long parsed = std::strtoll(value.c_str(), &end, 10);
    if (errno != 0 || end == value.c_str() || *end != '\0' || parsed <= 0 ||
        parsed > INT_MAX) {
        throw std::runtime_error(label + " is not a positive PID");
    }
    return static_cast<pid_t>(parsed);
}

inline std::string ReadFileLimited(const std::string& path,
                                   std::size_t maximum_size) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("failed to open runtime identity file: " + path);
    }
    std::string content;
    char buffer[4096];
    while (input) {
        input.read(buffer, sizeof(buffer));
        const std::streamsize count = input.gcount();
        if (count > 0) {
            if (content.size() + static_cast<std::size_t>(count) > maximum_size) {
                throw std::runtime_error(
                    "runtime identity file exceeds size limit: " + path);
            }
            content.append(buffer, static_cast<std::size_t>(count));
        }
    }
    if (!input.eof()) {
        throw std::runtime_error("failed to read runtime identity file: " + path);
    }
    return content;
}

inline std::vector<std::string> ReadProcessArguments(
    const std::string& proc_root,
    pid_t pid) {
    const std::string content = ReadFileLimited(
        proc_root + "/" + std::to_string(pid) + "/cmdline", 64 * 1024);
    std::vector<std::string> arguments;
    std::size_t position = 0;
    while (position < content.size()) {
        const std::size_t end = content.find('\0', position);
        if (end == std::string::npos) {
            throw std::runtime_error("process cmdline is not NUL terminated");
        }
        arguments.push_back(content.substr(position, end - position));
        position = end + 1;
    }
    return arguments;
}

inline std::vector<pid_t> ListServiceProcesses(const std::string& proc_root,
                                               pid_t main_pid) {
    std::vector<pid_t> pending{main_pid};
    std::vector<pid_t> processes;
    std::set<pid_t> seen;
    while (!pending.empty()) {
        const pid_t pid = pending.back();
        pending.pop_back();
        if (!seen.emplace(pid).second) {
            continue;
        }
        if (seen.size() > 256) {
            throw std::runtime_error("service process tree exceeds safety limit");
        }
        processes.push_back(pid);

        const std::string children_path =
            proc_root + "/" + std::to_string(pid) + "/task/" +
            std::to_string(pid) + "/children";
        std::ifstream children(children_path);
        if (!children) {
            continue;
        }
        std::string child_value;
        while (children >> child_value) {
            pending.push_back(ParsePid(child_value, "service child PID"));
        }
        if (!children.eof()) {
            throw std::runtime_error("failed to parse service child PIDs");
        }
    }
    return processes;
}

inline std::string BaseName(const std::string& path) {
    const std::size_t separator = path.find_last_of('/');
    return separator == std::string::npos ? path : path.substr(separator + 1);
}

inline pid_t FindEngineProcess(const std::string& proc_root,
                               pid_t main_pid,
                               const std::string& database_path) {
    std::vector<pid_t> matches;
    for (const pid_t pid : ListServiceProcesses(proc_root, main_pid)) {
        std::vector<std::string> arguments;
        try {
            arguments = ReadProcessArguments(proc_root, pid);
        } catch (const std::runtime_error&) {
            continue;
        }
        if (arguments.empty() ||
            BaseName(arguments.front()) != "kylin-ai-vector-engine") {
            continue;
        }
        bool database_seen = false;
        for (const std::string& argument : arguments) {
            if (argument == database_path) {
                database_seen = true;
                break;
            }
        }
        if (database_seen) {
            matches.push_back(pid);
        }
    }
    if (matches.size() != 1) {
        throw std::runtime_error(
            "expected exactly one service engine process with the manifest database; "
            "count=" + std::to_string(matches.size()));
    }
    return matches.front();
}

inline std::string FindSocketInode(const std::string& proc_root,
                                   const std::string& socket_path) {
    const std::string table = ReadFileLimited(proc_root + "/net/unix", 1024 * 1024);
    std::istringstream input(table);
    std::string line;
    std::vector<std::string> matches;
    while (std::getline(input, line)) {
        std::istringstream fields_input(line);
        std::vector<std::string> fields;
        std::string field;
        while (fields_input >> field) {
            fields.push_back(field);
        }
        if (fields.size() >= 8 && fields.back() == socket_path) {
            const std::string& inode = fields[6];
            if (inode.empty() ||
                !std::all_of(inode.begin(), inode.end(), [](char ch) {
                    return ch >= '0' && ch <= '9';
                }) ||
                inode == "0") {
                throw std::runtime_error("Vector Engine Unix Socket inode is invalid");
            }
            matches.push_back(inode);
        }
    }
    if (matches.size() != 1) {
        throw std::runtime_error(
            "expected exactly one Vector Engine Unix Socket entry; count=" +
            std::to_string(matches.size()));
    }
    return matches.front();
}

inline void RequireSocketOwnedByProcess(const std::string& proc_root,
                                        pid_t engine_pid,
                                        const std::string& socket_inode) {
    const std::string fd_path =
        proc_root + "/" + std::to_string(engine_pid) + "/fd";
    DIR* directory = ::opendir(fd_path.c_str());
    if (directory == nullptr) {
        throw std::runtime_error(
            "failed to open engine file descriptors: " +
            std::string(std::strerror(errno)));
    }

    const std::string expected = "socket:[" + socket_inode + "]";
    bool found = false;
    while (const struct dirent* entry = ::readdir(directory)) {
        if (entry->d_name[0] == '.') {
            continue;
        }
        const std::string descriptor = fd_path + "/" + entry->d_name;
        char target[PATH_MAX + 1] = {};
        const ssize_t length =
            ::readlink(descriptor.c_str(), target, sizeof(target) - 1);
        if (length < 0) {
            continue;
        }
        target[length] = '\0';
        if (expected == target) {
            found = true;
            break;
        }
    }
    const int close_result = ::closedir(directory);
    if (close_result != 0) {
        throw std::runtime_error("failed to close engine file descriptor directory");
    }
    if (!found) {
        throw std::runtime_error(
            "Vector Engine Unix Socket is not held by the manifest database process");
    }
}

inline RuntimeIdentity ValidateRuntimeIdentity(
    const Request& request,
    const std::map<std::string, std::string>& manifest,
    const RuntimePaths& paths = RuntimePaths()) {
    RuntimeIdentity identity;
    identity.executable_path = CanonicalPath(paths.self_exe);
    const struct stat executable =
        RequireCanonicalRegularFile(identity.executable_path, "cleanup executable");
    if ((executable.st_mode & (S_IWGRP | S_IWOTH)) != 0) {
        throw std::runtime_error(
            "cleanup executable must not be group/world writable");
    }

    const std::string default_self_exe = paths.proc_root + "/self/exe";
    const std::string executable_hash_target =
        paths.self_exe == default_self_exe
            ? paths.proc_root + "/" +
                  std::to_string(static_cast<unsigned long long>(::getpid())) +
                  "/exe"
            : paths.self_exe;
    const std::string hash_output =
        CaptureCommand(paths.sha256sum, {executable_hash_target});
    const std::size_t hash_separator = hash_output.find_first_of(" \t\r\n");
    identity.executable_sha256 = hash_output.substr(0, hash_separator);
    if (!IsHex(identity.executable_sha256, 64)) {
        throw std::runtime_error("cleanup executable returned an invalid SHA-256");
    }
    const std::string& manifest_binary = RequireValue(manifest, "binary_sha256");
    if (!HexEqual(identity.executable_sha256, manifest_binary)) {
        throw std::runtime_error(
            "actual /proc/self/exe SHA-256 does not match the cleanup manifest");
    }

    identity.service_unit = RequireValue(manifest, "service_unit");
    if (identity.service_unit.size() < 9 || identity.service_unit.front() == '-' ||
        identity.service_unit.compare(identity.service_unit.size() - 8, 8,
                                      ".service") != 0 ||
        !std::all_of(identity.service_unit.begin(), identity.service_unit.end(),
                     [](char ch) {
                         return (ch >= 'A' && ch <= 'Z') ||
                                (ch >= 'a' && ch <= 'z') ||
                                (ch >= '0' && ch <= '9') || ch == '_' || ch == '.' ||
                                ch == '@' || ch == ':' || ch == '-';
                     })) {
        throw std::runtime_error("cleanup manifest service_unit is invalid");
    }

    const std::string service_output = CaptureCommand(
        paths.systemctl,
        {"--user", "show", "--no-pager", "--property=LoadState",
         "--property=ActiveState", "--property=InvocationID",
         "--property=MainPID", identity.service_unit});
    const auto service = ParseKeyValueOutput(service_output, "systemctl output");
    RequireEqual(service, "LoadState", "loaded");
    RequireEqual(service, "ActiveState", "active");
    identity.invocation_id = RequireValue(service, "InvocationID");
    if (!IsHex(identity.invocation_id, 32) ||
        !HexEqual(identity.invocation_id, request.cleanup_invocation_id)) {
        throw std::runtime_error(
            "actual systemd InvocationID does not match the cleanup authorization");
    }
    identity.service_main_pid =
        ParsePid(RequireValue(service, "MainPID"), "systemd MainPID");

    const std::string proc_root = CanonicalPath(paths.proc_root);
    identity.engine_pid = FindEngineProcess(
        proc_root, identity.service_main_pid, request.database_path);
    identity.database_path = request.database_path;
    identity.socket_path = paths.socket_path.empty()
                               ? "/tmp/kylin-ai-vector-engine-" +
                                     std::to_string(static_cast<unsigned long long>(
                                         ::geteuid())) +
                                     ".sock"
                               : paths.socket_path;
    identity.socket_inode = FindSocketInode(proc_root, identity.socket_path);
    RequireSocketOwnedByProcess(
        proc_root, identity.engine_pid, identity.socket_inode);
    return identity;
}

}  // namespace D2Cleanup
