#!/bin/bash
# 阶段2: Socket路径审计 — VM端执行
set -e
echo "=== Stage 2 Socket Audit ==="

SDK=/home/kylin-agent/openkylin-build/kylin-ai-sdk
SRC=/home/kylin-agent/openkylin-build/kylin-aiassistant/kylin-aiassistant
RT=/home/kylin-agent/openkylin-build/kylin-ai-runtime
OUT=/home/kylin-agent/openkylin-build/socket_audit.log

exec > "$OUT" 2>&1

echo "=== SDK directory ==="
ls -la "$SDK" 2>/dev/null || echo "SDK DIR NOT FOUND"
echo ""

echo "=== Runtime directory ==="
ls -la "$RT" 2>/dev/null || echo "RT DIR NOT FOUND"
echo ""

echo "=== system kyai-assistant headers ==="
find /usr/include -maxdepth 3 -name "*kyai*" 2>/dev/null || echo "none"
echo ""

echo "=== system kyai-assistant libs ==="
find /usr/lib -maxdepth 2 -name "*kyai*assistant*" 2>/dev/null || echo "none"
echo ""

echo "=== QLocalSocket in full openkylin-build ==="
grep -rn "QLocalSocket\|connectToServer" /home/kylin-agent/openkylin-build/kylin-aiassistant/ --include="*.cpp" --include="*.h" 2>/dev/null | head -20 || echo "none"
echo ""

echo "=== OsAssistant class definition ==="
grep -rn "class.*OsAssistant" /usr/include/ 2>/dev/null | head -5 || echo "not in headers"
echo ""

echo "=== kyai::assistant namespace ==="
grep -rn "namespace kyai\|namespace assistant" /home/kylin-agent/openkylin-build/ --include="*.h" --include="*.cpp" 2>/dev/null | head -10 || echo "none"
echo ""

echo "=== sendToolMessage path ==="
grep -rn "sendToolMessage\|toolMessage\|ToolResult" "$SRC" --include="*.cpp" --include="*.h" 2>/dev/null | head -20 || echo "none"
echo ""

echo "AUDIT COMPLETE"