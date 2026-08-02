// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <sys/stat.h>
#include <unistd.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <map>
#include <stdexcept>
#include <string>

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

inline void Validate(const Request& request) {
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
}

}  // namespace D2Cleanup
