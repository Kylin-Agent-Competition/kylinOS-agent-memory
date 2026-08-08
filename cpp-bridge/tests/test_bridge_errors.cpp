/**
 * test_bridge_errors.cpp
 *
 * 轨道 A — C++ 层错误映射测试（Day4）
 *
 * 验证 embedding_bridge.h 在未加载/未建会话时的错误码映射，
 * 不依赖麒麟 SDK（无 .so 也可运行）。
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

int main() {
    std::printf("=== test_bridge_errors ===\n");

    // 1. 未加载时 embed → ERR_DLOPEN_FAILED
    {
        EmbeddingBridge bridge;
        auto r = bridge.embed("hello");
        CHECK(r.is_fail(), "未加载时 embed 返回失败");
        CHECK(r.error == BridgeError::ERR_DLOPEN_FAILED,
              "未加载时 embed 错误码 = ERR_DLOPEN_FAILED");
    }

    // 2. 未加载时 create_session → ERR_DLOPEN_FAILED
    {
        EmbeddingBridge bridge;
        auto r = bridge.create_session();
        CHECK(r.is_fail(), "未加载时 create_session 返回失败");
        CHECK(r.error == BridgeError::ERR_DLOPEN_FAILED,
              "未加载时 create_session 错误码 = ERR_DLOPEN_FAILED");
    }

    // 3. BridgeResult 基本语义
    {
        auto ok = BridgeResult<int>::ok(768);
        auto fail = BridgeResult<int>::fail(BridgeError::ERR_TIMEOUT, "timeout");
        CHECK(ok.is_ok() && ok.value.has_value() && ok.value.value() == 768,
              "BridgeResult::ok 携带值");
        CHECK(fail.is_fail() && fail.error == BridgeError::ERR_TIMEOUT,
              "BridgeResult::fail 携带错误码");
        CHECK(!fail.value.has_value(), "BridgeResult::fail 无值");
    }

    // 4. 错误码枚举无重叠（抽查关键值）
    {
        bool dup = false;
        BridgeError codes[] = {
            BridgeError::SUCCESS,           BridgeError::UNKNOWN,
            BridgeError::NOT_IMPLEMENTED,   BridgeError::ERR_SO_NOT_FOUND,
            BridgeError::ERR_DLOPEN_FAILED, BridgeError::ERR_DLSYM_FAILED,
            BridgeError::ERR_SESSION_CREATE, BridgeError::ERR_SESSION_INIT,
            BridgeError::ERR_SESSION_DESTROY, BridgeError::ERR_SESSION_DESTROYED,
            BridgeError::ERR_FATAL_FAILURE,
            BridgeError::ERR_EMBED_CALL,
            BridgeError::ERR_EMBED_RESULT,  BridgeError::ERR_EMBED_ERROR,
            BridgeError::ERR_TIMEOUT,       BridgeError::ERR_CANCELLED,
            BridgeError::ERR_MODEL_NOT_LOADED, BridgeError::ERR_MODEL_INVALID,
        };
        int n = sizeof(codes) / sizeof(codes[0]);
        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                if ((uint32_t)codes[i] == (uint32_t)codes[j]) dup = true;
            }
        }
        CHECK(!dup, "错误码枚举无重叠");
    }

    // 5. load() 失败后重试（syms_ 清零验证）：用不存在 .so → ERR_SO_NOT_FOUND
    {
        BridgeInitParams params;
        params.so_path = "/tmp/definitely_not_exist_load_retry.so";
        EmbeddingBridge bridge(params);
        auto r1 = bridge.load();
        CHECK(r1.is_fail() && r1.error == BridgeError::ERR_SO_NOT_FOUND,
              "load() 不存在 .so → ERR_SO_NOT_FOUND");
        // 再次 load() 仍应失败（不崩溃、不残留悬空符号）
        auto r2 = bridge.load();
        CHECK(r2.is_fail(), "load() 重试仍返回失败（每次真实重试）");
        CHECK(bridge.is_loaded() == false, "load() 失败后 is_loaded()=false");
    }

    // 6. create_session() 幂等性（无 .so 时应在 !handle_ 分支失败）
    {
        BridgeInitParams params;
        params.so_path = "/tmp/definitely_not_exist_create_idem.so";
        EmbeddingBridge bridge(params);
        auto r1 = bridge.create_session();
        CHECK(r1.is_fail() && r1.error == BridgeError::ERR_DLOPEN_FAILED,
              "未 load 时 create_session → ERR_DLOPEN_FAILED");
    }

    // 7. embed() 无会话（已加载但未建会话）→ ERR_SESSION_INIT
    //    需真实 .so 才能走到此分支；无 .so 时走 !handle_ 分支，
    //    此处仅验证 !handle_ 分支（ERR_DLOPEN_FAILED）不崩溃。
    {
        BridgeInitParams params;
        params.so_path = "/tmp/definitely_not_exist_embed_ready.so";
        EmbeddingBridge bridge(params);
        auto r = bridge.embed("hello");
        CHECK(r.is_fail() && r.error == BridgeError::ERR_DLOPEN_FAILED,
              "未加载时 embed → ERR_DLOPEN_FAILED（无 .so 环境）");
    }

    std::printf("=== 结果: %s (%d failures) ===\n",
                failures == 0 ? "PASS" : "FAIL", failures);
    return failures == 0 ? 0 : 1;
}
