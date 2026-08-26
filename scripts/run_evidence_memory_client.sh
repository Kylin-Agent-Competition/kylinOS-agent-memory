#!/bin/bash
set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$SCRIPT_DIR/.." && pwd)

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$REPO/evidence/memory-client"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ctest_qml_on_${TS}.txt"
SMOKE_LOG="$LOG_DIR/qml_startup_smoke_${TS}.txt"
RUN_ID="run_${TS}"

echo "=== EVIDENCE RUN HEADER ===" > "$LOG"
echo "RUN_ID: ${RUN_ID}" >> "$LOG"
echo "DATE: $(date -Iseconds)" >> "$LOG"
echo "REPO_PATH: ${REPO}" >> "$LOG"
echo "WORKDIR_ABS: $(pwd)" >> "$LOG"

cd "$REPO"

echo "BRANCH: $(git branch --show-current)" >> "$LOG"
HEAD_SHA=$(git rev-parse HEAD)
echo "HEAD_SHA: ${HEAD_SHA}" >> "$LOG"
echo "TESTED_COMMIT: ${HEAD_SHA}" >> "$LOG"
echo "UNAME: $(uname -a)" >> "$LOG"
echo "GCC: $(gcc --version | head -1)" >> "$LOG"
echo "CMAKE: $(cmake --version | head -1)" >> "$LOG"
echo "QTBASE5_DEV: $(dpkg -l qtbase5-dev 2>/dev/null | tail -1)" >> "$LOG"
echo "QTDECLARATIVE5_DEV: $(dpkg -l qtdeclarative5-dev 2>/dev/null | tail -1)" >> "$LOG"
echo "QTQUICKCONTROLS2_5_DEV: $(dpkg -l qtquickcontrols2-5-dev 2>/dev/null | tail -1)" >> "$LOG"

echo "" >> "$LOG"
echo "=== CLEAN BUILD (QML_APP=ON, TESTS=ON) ===" >> "$LOG"
echo "COMMAND: rm -rf memory-client/build" >> "$LOG"
rm -rf memory-client/build
CMAKE_CMD="cmake -S memory-client -B memory-client/build -DKYLIN_MEMORY_CLIENT_BUILD_QML_APP=ON -DKYLIN_MEMORY_CLIENT_BUILD_TESTS=ON"
echo "COMMAND: ${CMAKE_CMD}" >> "$LOG"
bash -c "$CMAKE_CMD" >> "$LOG" 2>&1
CMAKE_RC=$?
echo "CMAKE_RC=${CMAKE_RC}" >> "$LOG"
if [ "$CMAKE_RC" -ne 0 ]; then
  echo "STATUS: CMAKE_FAILED"
  exit 1
fi

BUILD_CMD="cmake --build memory-client/build --parallel"
echo "COMMAND: ${BUILD_CMD}" >> "$LOG"
bash -c "$BUILD_CMD" >> "$LOG" 2>&1
BUILD_RC=$?
echo "BUILD_RC=${BUILD_RC}" >> "$LOG"
if [ "$BUILD_RC" -ne 0 ]; then
  echo "STATUS: BUILD_FAILED"
  exit 2
fi

echo "" >> "$LOG"
echo "=== BUILD ARTIFACTS ===" >> "$LOG"
find memory-client/build -maxdepth 2 -type f \( -name "test_*" -o -name "kylin-memory-client" -o -name "*.a" \) -ls >> "$LOG" 2>&1

echo "" >> "$LOG"
echo "=== CTEST -V (cd memory-client/build) ===" >> "$LOG"
CTEST_CMD="ctest -V"
echo "COMMAND: cd memory-client/build && ${CTEST_CMD}" >> "$LOG"
( cd memory-client/build && bash -c "$CTEST_CMD" ) >> "$LOG" 2>&1
CTEST_RC=$?
echo "CTEST_RC=${CTEST_RC}" >> "$LOG"

echo "" >> "$LOG"
echo "=== CTEST SUMMARY ===" >> "$LOG"
grep -E "^\s*[0-9]+/[0-9]+ test|Passed|Failed|Total Test|Test #|tests passed|tests failed" "$LOG" | tail -40 >> "$LOG" || true

echo ""
echo "LOG: ${LOG}"
echo "HEAD_SHA: ${HEAD_SHA}"
echo "CTEST_RC: ${CTEST_RC}"
echo "LOG_SIZE: $(wc -c < "$LOG") bytes"

# Now run QML startup smoke with real exit code
echo ""
echo "=== QML STARTUP SMOKE ==="
(
  echo "=== QML STARTUP SMOKE HEADER ==="
  echo "RUN_ID: ${RUN_ID}"
  echo "DATE: $(date -Iseconds)"
  echo "HEAD_SHA: ${HEAD_SHA}"
  echo "EXE: $REPO/memory-client/build/kylin-memory-client"
  echo "COMMAND: QT_QPA_PLATFORM=offscreen timeout 3 ./memory-client/build/kylin-memory-client"
  echo "---BEGIN-STDOUT/STDERR---"
) > "$SMOKE_LOG"

export QT_QPA_PLATFORM=offscreen
timeout 3 "$REPO/memory-client/build/kylin-memory-client" >> "$SMOKE_LOG" 2>&1
SMOKE_RC=$?

{
  echo "---END-STDOUT/STDERR---"
  echo "EXIT_CODE=${SMOKE_RC}"
  if [ "${SMOKE_RC}" = "124" ]; then
    echo "EXPECTED_TIMEOUT=true"
    echo "RESULT=PASS (timeout killed long-running app; no load failure)"
  elif [ "${SMOKE_RC}" = "0" ]; then
    echo "EXPECTED_TIMEOUT=false"
    echo "RESULT=PASS (app exited cleanly within 3s)"
  else
    echo "EXPECTED_TIMEOUT=any"
    echo "RESULT=CHECK (exit code ${SMOKE_RC})"
  fi
  echo "CHECK: no 'module not installed' error?"
  grep -cE "module.*not installed|is not a type|failed to load component" "$SMOKE_LOG" | head -5
  echo "CHECK: rootObjects?"
  grep -c "rootObjects" "$SMOKE_LOG" | head -5
} >> "$SMOKE_LOG" 2>&1 || true

echo "SMOKE_LOG: ${SMOKE_LOG}"
echo "SMOKE_RC: ${SMOKE_RC}"
echo "SMOKE_LAST_LINE: $(tail -1 "$SMOKE_LOG")"

# Checksums
echo ""
echo "=== SHA256 CHECKSUMS ==="
EVIDENCE_FILES=(
  "$LOG"
  "$SMOKE_LOG"
)
for f in "${EVIDENCE_FILES[@]}"; do
  (cd "$(dirname "$f")" && sha256sum "$(basename "$f")")
done

echo ""
echo "RUN_ID: ${RUN_ID}"
echo "HEAD_SHA: ${HEAD_SHA}"
echo "DONE."
