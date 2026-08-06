/**
 * test_bridge_destroyed.cpp
 *
 * 轨道 A — Bridge destroy 终态测试（P1-1，假 .so）
 *
 * 验证 destroy_session() 后进入不可恢复终态（ERR_SESSION_DESTROYED）：
 *   load → create_session → embed("") → destroy_session
 *   → create_session 返回 ERR_SESSION_DESTROYED
 *   → embed 返回 ERR_SESSION_DESTROYED
 *   → 重复 destroy_session 幂等（仍返回 ok）
 *
 * 依赖：fake_sdk_malformed.c 编译的 .so 路径由 argv[1] 传入。
 */

#include "embedding_bridge.h"

#include <cstdio>

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
    std::printf("=== test_bridge_destroyed ===\n");
    if (argc < 2) {
        std::printf("  [FAIL] 用法: %s <fake_sdk.so>\n", argv[0]);
        return 1;
    }

    BridgeInitParams params;
    params.so_path = argv[1];
    EmbeddingBridge bridge(params);

    // 1. load + create_session + embed
    auto rl = bridge.load();
    CHECK(rl.is_ok(), "load 成功");
    auto rc = bridge.create_session();
    CHECK(rc.is_ok(), "create_session 成功");
    auto re = bridge.embed("");
    CHECK(re.is_ok(), "embed 成功");
    CHECK(re.value->dimension == 768, "embed 维度=768");

    // 2. destroy_session → 进入终态
    auto rd = bridge.destroy_session();
    CHECK(rd.is_ok(), "destroy_session 成功");
    CHECK(bridge.has_session() == false, "destroy 后 has_session=false");
    CHECK(bridge.is_loaded() == true, "destroy 后 is_loaded=true（.so 不卸载）");
    CHECK(bridge.session_destroyed() == true, "destroy 后 session_destroyed=true");

    // 3. 再次 create_session → ERR_SESSION_DESTROYED
    auto rc2 = bridge.create_session();
    CHECK(rc2.is_fail(), "destroy 后 create_session 返回失败");
    CHECK(rc2.error == BridgeError::ERR_SESSION_DESTROYED,
          "destroy 后 create_session 错误码 = ERR_SESSION_DESTROYED");

    // 4. embed → ERR_SESSION_DESTROYED
    auto re2 = bridge.embed("hello");
    CHECK(re2.is_fail(), "destroy 后 embed 返回失败");
    CHECK(re2.error == BridgeError::ERR_SESSION_DESTROYED,
          "destroy 后 embed 错误码 = ERR_SESSION_DESTROYED");

    // 5. 重复 destroy_session → 幂等（仍返回 ok）
    auto rd2 = bridge.destroy_session();
    CHECK(rd2.is_ok(), "重复 destroy_session 幂等返回 ok");

    std::printf("=== 结果: %s (%d failures) ===\n",
                failures == 0 ? "PASS" : "FAIL", failures);
    return failures == 0 ? 0 : 1;
}
