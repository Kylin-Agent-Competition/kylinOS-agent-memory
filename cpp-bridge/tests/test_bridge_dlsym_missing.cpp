/**
 * test_bridge_dlsym_missing.cpp
 *
 * 轨道 A — dlsym 缺失失败路径测试（P1-High/P1-3，假 .so 符号缺失变体）
 *
 * 验证方案 A（不可恢复终态）在"dlopen 成功但必需符号缺失"阶段的行为：
 *   1. load() → 必需符号 dlsym 缺失 → ERR_FATAL_FAILURE + fatal_failure_=true
 *   2. 同一 Bridge 重试 load() → 仍 ERR_FATAL_FAILURE（不重新 dlopen）
 *   3. create_session() / embed() 在 fatal 态 → ERR_FATAL_FAILURE
 *
 * 依赖：fake_sdk_malformed.c 以 FAKE_MISSING_CREATE_SESSION 编译的 .so
 *       （不导出 text_embedding_create_session），路径由 argv[1] 传入。
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
    std::printf("=== test_bridge_dlsym_missing ===\n");
    if (argc < 2) {
        std::printf("  [FAIL] 用法: %s <fake_sdk_missing_dlsym.so>\n", argv[0]);
        return 1;
    }
    const char* so = argv[1];

    BridgeInitParams params;
    params.so_path = so;
    EmbeddingBridge bridge(params);

    // 1. load：dlsym 缺失 → ERR_FATAL_FAILURE + fatal 终态
    auto rl = bridge.load();
    CHECK(rl.is_fail() && rl.error == BridgeError::ERR_FATAL_FAILURE,
          "必需符号缺失 → ERR_FATAL_FAILURE（方案 A 不可恢复）");
    CHECK(bridge.fatal_failure() == true,
          "dlsym 缺失置 fatal（禁止重试 dlopen）");
    CHECK(bridge.is_loaded() == false,
          "fatal 后 handle_ 为空（已 dlclose）");

    // 2. 同一 Bridge 重试 load：稳定 ERR_FATAL_FAILURE，不重新 dlopen
    auto rl2 = bridge.load();
    CHECK(rl2.is_fail() && rl2.error == BridgeError::ERR_FATAL_FAILURE,
          "重试 load → ERR_FATAL_FAILURE（不触发 dlclose→dlopen）");

    // 3. fatal 态下 create_session / embed 均稳定报错
    auto rc = bridge.create_session();
    CHECK(rc.is_fail() && rc.error == BridgeError::ERR_FATAL_FAILURE,
          "fatal 态 create_session → ERR_FATAL_FAILURE");
    auto re = bridge.embed("x");
    CHECK(re.is_fail() && re.error == BridgeError::ERR_FATAL_FAILURE,
          "fatal 态 embed → ERR_FATAL_FAILURE");

    std::printf("=== 结果: %s (%d failures) ===\n",
                failures == 0 ? "PASS" : "FAIL", failures);
    return failures == 0 ? 0 : 1;
}
