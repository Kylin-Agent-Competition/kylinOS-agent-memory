#!/bin/bash
# R3 standalone test runner — run on Kylin VM
set -euo pipefail
REPO=/home/kylin-agent/kylin-memory-echo
OUT=/tmp/r3_result.txt

cd "${REPO}/os-agent-integration/echo"

# Rebuild
rm -rf build
cmake -S . -B build > /dev/null 2>&1
cmake --build build > /dev/null 2>&1
mkdir -p "${REPO}/bin"
cp build/kaiming_memory_client "${REPO}/bin/"
chmod +x "${REPO}/bin/kaiming_memory_client"

# Run test
echo "=== R3 TEST START $(date -Iseconds) ===" > "${OUT}"
bash test_systemd_lifecycle.sh >> "${OUT}" 2>&1
echo "EC=$?" >> "${OUT}"
echo "=== R3 TEST END $(date -Iseconds) ===" >> "${OUT}"
echo "DONE" > /tmp/r3_done.flag