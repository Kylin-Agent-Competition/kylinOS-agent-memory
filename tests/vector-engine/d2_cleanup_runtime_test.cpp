// SPDX-License-Identifier: Apache-2.0

#include <exception>
#include <iostream>

#include "d2_cleanup_manifest.h"

int main(int argc, char** argv) {
    if (argc != 13) {
        std::cerr
            << "usage: d2_cleanup_runtime_test <manifest> <token> "
               "<invocation-id> <run-id> <collection> <app-id> <database> "
               "<proc-root> <systemctl> <sha256sum> <self-exe> <socket-path>\n";
        return 2;
    }

    try {
        const D2Cleanup::Request request = {
            argv[1], argv[2], argv[3], argv[4], argv[5], argv[6], argv[7]};
        const auto manifest = D2Cleanup::ValidateManifest(request);
        D2Cleanup::RuntimePaths paths;
        paths.proc_root = argv[8];
        paths.systemctl = argv[9];
        paths.sha256sum = argv[10];
        paths.self_exe = argv[11];
        paths.socket_path = argv[12];
        const auto identity =
            D2Cleanup::ValidateRuntimeIdentity(request, manifest, paths);
        std::cout << "engine_pid=" << identity.engine_pid
                  << " invocation_id=" << identity.invocation_id
                  << " executable_sha256=" << identity.executable_sha256
                  << " socket_inode=" << identity.socket_inode << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
