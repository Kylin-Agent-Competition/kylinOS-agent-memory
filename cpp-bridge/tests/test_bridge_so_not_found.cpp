/**
 * test_bridge_so_not_found.cpp
 *
 * 轨道 A — .so 不存在时的错误映射测试（Day4）
 *
 * 用不存在的 so_path 触发 ERR_SO_NOT_FOUND，验证错误码映射。
 * 不依赖麒麟 SDK（无真实 .so 也可运行）。
 */

#include "embedding_bridge.h"

#include <cstdio>

using namespace kylin;

int main() {
    std::printf("=== test_bridge_so_not_found ===\n");

    // 构造不存在的 .so 路径
    BridgeInitParams params;
    params.so_path = "/tmp/definitely_not_exist.so.1";

    EmbeddingBridge bridge(params);
    auto r = bridge.load();

    if (r.is_fail() && r.error == BridgeError::ERR_SO_NOT_FOUND) {
        std::printf("  [PASS] 不存在的 so_path → ERR_SO_NOT_FOUND\n");
        std::printf("  消息: %s\n", r.error_message.c_str());
        return 0;
    }

    std::printf("  [FAIL] 期望 ERR_SO_NOT_FOUND, 实际 error=%u\n",
                static_cast<uint32_t>(r.error));
    return 1;
}
