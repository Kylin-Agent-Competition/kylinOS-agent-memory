// SPDX-License-Identifier: Apache-2.0

#include <exception>
#include <iostream>

#include "d2_cleanup_manifest.h"

int main(int argc, char** argv) {
    if (argc != 8) {
        std::cerr << "usage: d2_cleanup_manifest_test <manifest> <token> "
                     "<invocation-id> <run-id> <collection> <app-id> <database>\n";
        return 2;
    }

    try {
        D2Cleanup::Validate(
            {argv[1], argv[2], argv[3], argv[4], argv[5], argv[6], argv[7]});
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
