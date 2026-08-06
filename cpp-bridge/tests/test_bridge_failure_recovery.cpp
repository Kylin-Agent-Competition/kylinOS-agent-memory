/**
 * test_bridge_failure_recovery.cpp
 *
 * 轨道 A — 失败恢复策略测试（P1-High/P1-3，假 .so）
 *
 * 验证失败阶段的恢复策略（方案 A：不可恢复终态）：
 *   1. .so 不存在 → ERR_SO_NOT_FOUND，不置 fatal（可换路径重试）
 *   2. init_session 失败 → ERR_FATAL_FAILURE + fatal_failure_=true，重试 create 返回 ERR_FATAL_FAILURE
 *   3. create_session 返回 NULL → ERR_SESSION_CREATE，不置 fatal（未执行 destroy，可安全重试）
 *   4. destroy 终态 → ERR_SESSION_DESTROYED（P0-2 回归）
 * dlsym 缺失路径（必需符号缺失 → ERR_FATAL_FAILURE）由独立测试
 * test_bridge_dlsym_missing.cpp 覆盖（fake_sdk 符号缺失变体 .so）。
 *
 * 依赖：fake_sdk_malformed.c 编译的 .so 路径由 argv[1] 传入。
 */

#include "embedding_bridge.h"

#include <cstdio>
#include <cstdlib>

using namespace kylin;

static int failures = 0;

#define CHECK(cond, name)                                                \
    do {                                                                 \
        if (cond) {                                                      \
            std::printf("  [PASS] %s\n", name);                          \
        } else {                                                         \
            std::printf("  [FAIL] %s\n", name);                          \
            failures++;                                                  \
        }                                                                \
    } while (0)

int main(int argc, char** argv) {
    std::printf("=== test_bridge_failure_recovery ===\n");
    if (argc < 2) {
        std::printf("  [FAIL] 用法: %s <fake_sdk.so>\n", argv[0]);
        return 1;
    }
    const char* so = argv[1];

    // ── 1. .so 不存在 → ERR_SO_NOT_FOUND（不置 fatal，可换路径重试） ──
    {
        BridgeInitParams params;
        params.so_path = "/tmp/definitely_not_exist.so.1";
        EmbeddingBridge bridge(params);
        auto r = bridge.load();
        CHECK(r.is_fail() && r.error == BridgeError::ERR_SO_NOT_FOUND,
              ".so 不存在 → ERR_SO_NOT_FOUND");
        CHECK(bridge.fatal_failure() == false,
              ".so 不存在不置 fatal（可换路径重试）");
    }

    // ── 2. init_session 失败 → ERR_FATAL_FAILURE + 不可恢复 ──
    {
        setenv("FAKE_MALFORMED", "initfail", 1);
        BridgeInitParams params;
        params.so_path = so;
        EmbeddingBridge bridge(params);
        auto rl = bridge.load();
        CHECK(rl.is_ok(), "load 成功（initfail 不影响 load）");
        auto rc = bridge.create_session();
        CHECK(rc.is_fail() && rc.error == BridgeError::ERR_FATAL_FAILURE,
              "init_session 失败 → ERR_FATAL_FAILURE");
        CHECK(bridge.fatal_failure() == true,
              "init_session 失败置 fatal（禁止重试）");
        // 重试 create_session → 仍 ERR_FATAL_FAILURE
        auto rc2 = bridge.create_session();
        CHECK(rc2.is_fail() && rc2.error == BridgeError::ERR_FATAL_FAILURE,
              "重试 create_session → ERR_FATAL_FAILURE（不触发 destroy→create）");
        unsetenv("FAKE_MALFORMED");
    }

    // ── 3. create_session 返回 NULL（FAKE_MALFORMED=createnull）→ ERR_SESSION_CREATE，可重试 ──
    {
        setenv("FAKE_MALFORMED", "createnull", 1);
        BridgeInitParams params;
        params.so_path = so;
        EmbeddingBridge bridge(params);
        auto rl = bridge.load();
        CHECK(rl.is_ok(), "load 成功（createnull 不影响 load）");
        auto rc = bridge.create_session();
        CHECK(rc.is_fail() && rc.error == BridgeError::ERR_SESSION_CREATE,
              "create_session NULL → ERR_SESSION_CREATE");
        CHECK(bridge.fatal_failure() == false,
              "create_session NULL 不置 fatal（未执行 destroy，可安全重试）");
        unsetenv("FAKE_MALFORMED");
    }

    // ── 4. dlsym 缺失（用不存在符号的 .so）→ ERR_FATAL_FAILURE ──
    // 注：dlsym 缺失的正式覆盖见 test_bridge_dlsym_missing.cpp（独立假 .so 变体）；
    // 此处通过 load 成功后立即 embed 验证正常路径，并回归 destroy 终态。
    {
        BridgeInitParams params;
        params.so_path = so;
        EmbeddingBridge bridge(params);
        // 正常 load + create + embed 确认基础可用
        auto rl = bridge.load();
        CHECK(rl.is_ok(), "正常 .so load 成功");
        auto rc = bridge.create_session();
        CHECK(rc.is_ok(), "正常 create_session 成功");
        auto re = bridge.embed("x");
        CHECK(re.is_ok() && re.value->dimension == 768, "正常 embed 768 维");
        // destroy 后终态（P0-2 回归）
        auto rd = bridge.destroy_session();
        CHECK(rd.is_ok(), "destroy_session ok");
        auto rc2 = bridge.create_session();
        CHECK(rc2.is_fail() && rc2.error == BridgeError::ERR_SESSION_DESTROYED,
              "destroy 后 create_session → ERR_SESSION_DESTROYED");
    }

    std::printf("=== 结果: %s (%d failures) ===\n",
                failures == 0 ? "PASS" : "FAIL", failures);
    return failures == 0 ? 0 : 1;
}
