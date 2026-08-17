/**
 * test_bridge_malformed.cpp
 *
 * 轨道 A — 畸形 SDK 结果防御测试（P0-2）
 *
 * 使用可控假 .so（fake_sdk_malformed.c）验证 embed() 对畸形结果的防御：
 *   FAKE_MALFORMED=null    → result=NULL         → ERR_EMBED_RESULT
 *   FAKE_MALFORMED=dim0    → dimension=0         → ERR_EMBED_RESULT
 *   FAKE_MALFORMED=datnull → data=NULL           → ERR_EMBED_RESULT
 *   FAKE_MALFORMED=nan     → 含 NaN              → ERR_EMBED_RESULT
 *   FAKE_MALFORMED=inf     → 含 Inf              → ERR_EMBED_RESULT
 *   默认（无 env）          → 正常 768 维          → ok
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

static BridgeResult<EmbeddingVector> run_with_mode(const char* so_path,
                                                   const char* mode) {
    setenv("FAKE_MALFORMED", mode, 1);
    BridgeInitParams params;
    params.so_path = so_path;
    EmbeddingBridge bridge(params);
    auto rl = bridge.load();
    if (rl.is_fail()) {
        return BridgeResult<EmbeddingVector>::fail(rl.error, rl.error_message);
    }
    auto rc = bridge.create_session();
    if (rc.is_fail()) {
        return BridgeResult<EmbeddingVector>::fail(rc.error, rc.error_message);
    }
    return bridge.embed("hello");
}

int main(int argc, char** argv) {
    std::printf("=== test_bridge_malformed ===\n");
    if (argc < 2) {
        std::printf("  [FAIL] 用法: %s <fake_sdk.so>\n", argv[0]);
        return 1;
    }
    const char* so = argv[1];

    // 1. 正常结果 → ok, dim=768
    {
        auto r = run_with_mode(so, "none");
        CHECK(r.is_ok(), "正常结果返回 ok");
        if (r.is_ok()) {
            CHECK(r.value->dimension == 768, "正常结果 dimension=768");
            CHECK(r.value->data.size() == 768, "正常结果 data.size=768");
        }
    }

    // 2. result=NULL → ERR_EMBED_RESULT
    {
        auto r = run_with_mode(so, "null");
        CHECK(r.is_fail(), "result=NULL 返回失败");
        CHECK(r.error == BridgeError::ERR_EMBED_RESULT,
              "result=NULL 错误码 = ERR_EMBED_RESULT");
    }

    // 3. dim=0 → ERR_EMBED_RESULT
    {
        auto r = run_with_mode(so, "dim0");
        CHECK(r.is_fail(), "dim=0 返回失败");
        CHECK(r.error == BridgeError::ERR_EMBED_RESULT,
              "dim=0 错误码 = ERR_EMBED_RESULT");
    }

    // 4. data=NULL → ERR_EMBED_RESULT
    {
        auto r = run_with_mode(so, "datnull");
        CHECK(r.is_fail(), "data=NULL 返回失败");
        CHECK(r.error == BridgeError::ERR_EMBED_RESULT,
              "data=NULL 错误码 = ERR_EMBED_RESULT");
    }

    // 5. 含 NaN → ERR_EMBED_RESULT
    {
        auto r = run_with_mode(so, "nan");
        CHECK(r.is_fail(), "含 NaN 返回失败");
        CHECK(r.error == BridgeError::ERR_EMBED_RESULT,
              "含 NaN 错误码 = ERR_EMBED_RESULT");
    }

    // 6. 含 Inf → ERR_EMBED_RESULT
    {
        auto r = run_with_mode(so, "inf");
        CHECK(r.is_fail(), "含 Inf 返回失败");
        CHECK(r.error == BridgeError::ERR_EMBED_RESULT,
              "含 Inf 错误码 = ERR_EMBED_RESULT");
    }

    // 7. text_embedding 返回 false → ERR_EMBED_CALL（P2 补充）
    {
        auto r = run_with_mode(so, "embedfalse");
        CHECK(r.is_fail(), "embed 返回 false 时失败");
        CHECK(r.error == BridgeError::ERR_EMBED_CALL,
              "embed false 错误码 = ERR_EMBED_CALL");
    }

    unsetenv("FAKE_MALFORMED");
    std::printf("=== 结果: %s (%d failures) ===\n",
                failures == 0 ? "PASS" : "FAIL", failures);
    return failures == 0 ? 0 : 1;
}
