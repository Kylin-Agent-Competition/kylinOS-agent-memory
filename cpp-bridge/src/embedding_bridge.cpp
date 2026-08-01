/**
 * embedding_bridge.cpp
 *
 * 轨道 A — Embedding C++ Bridge 实现
 *
 * 实现 dlopen/dlsym 真实调用路径，错误码映射见 bridge_error_contract.h。
 * 依赖：embedding_abi_compat.h（符号声明）、bridge_error_contract.h（错误契约）。
 */

#include "embedding_bridge.h"

#include <dlfcn.h>
#include <cmath>
#include <cstdio>
#include <unistd.h>

namespace kylin {

EmbeddingBridge::EmbeddingBridge(const BridgeInitParams& params)
    : params_(params) {}

EmbeddingBridge::~EmbeddingBridge() {
    // 析构时确保释放（不抛异常）。
    // 不加锁：析构时不应有并发访问；调用方应在析构前先 destroy_session()。
    destroy_unlocked();
}

BridgeStatus EmbeddingBridge::load() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (handle_) {
        return BridgeStatus::ok(std::monostate{});  // 幂等：已加载
    }

    // 1. 检查 .so 文件存在性 → ERR_SO_NOT_FOUND
    if (access(params_.so_path.c_str(), F_OK) != 0) {
        return BridgeStatus::fail(BridgeError::ERR_SO_NOT_FOUND,
                                  "so not found: " + params_.so_path);
    }

    // 2. dlopen → ERR_DLOPEN_FAILED
    void* h = dlopen(params_.so_path.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!h) {
        return BridgeStatus::fail(BridgeError::ERR_DLOPEN_FAILED, dlerror());
    }

    // 3. 解析符号 → ERR_DLSYM_FAILED（先写入局部变量，全部验证后再一次性赋给成员）
    EmbeddingSdkSymbols tmp;
    tmp.create_session =
        (TextEmbeddingSession* (*)(void))dlsym(h, "text_embedding_create_session");
    tmp.destroy_session =
        (void (*)(TextEmbeddingSession**))dlsym(h, "text_embedding_destroy_session");
    tmp.init_session =
        (int (*)(TextEmbeddingSession*))dlsym(h, "text_embedding_init_session");
    tmp.enable_event_loop =
        (void (*)(TextEmbeddingSession*, bool))dlsym(h, "text_embedding_enable_internal_event_loop");
    tmp.embed =
        (bool (*)(TextEmbeddingSession*, const char*, EmbeddingResult**))dlsym(h, "text_embedding");
    tmp.result_vector_data =
        (float* (*)(EmbeddingResult*))dlsym(h, "embedding_result_get_vector_data");
    tmp.result_vector_length =
        (int (*)(EmbeddingResult*))dlsym(h, "embedding_result_get_vector_length");
    tmp.result_error_code =
        (int (*)(EmbeddingResult*))dlsym(h, "embedding_result_get_error_code");
    tmp.result_error_message =
        (const char* (*)(EmbeddingResult*))dlsym(h, "embedding_result_get_error_message");
    tmp.result_destroy =
        (void (*)(EmbeddingResult**))dlsym(h, "embedding_result_destroy");
    // 模型接口可选（Day4 骨架不强制）
    tmp.init_model =
        (int (*)(TextEmbeddingSession*, const char*))dlsym(h, "text_embedding_init_model");

    // 必需符号检查
    if (!tmp.create_session || !tmp.destroy_session || !tmp.init_session ||
        !tmp.enable_event_loop || !tmp.embed ||
        !tmp.result_vector_data || !tmp.result_vector_length ||
        !tmp.result_error_code || !tmp.result_error_message ||
        !tmp.result_destroy) {
        dlclose(h);
        return BridgeStatus::fail(BridgeError::ERR_DLSYM_FAILED,
                                  "required symbol missing from " + params_.so_path);
    }

    syms_ = tmp;  // 全部验证后一次性赋值
    handle_ = h;
    return BridgeStatus::ok(std::monostate{});
}

BridgeStatus EmbeddingBridge::create_session() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!handle_) {
        return BridgeStatus::fail(BridgeError::ERR_DLOPEN_FAILED, "bridge not loaded");
    }
    if (session_) {
        return BridgeStatus::ok(std::monostate{});  // 幂等：已有会话
    }

    TextEmbeddingSession* s = syms_.create_session();
    if (!s) {
        return BridgeStatus::fail(BridgeError::ERR_SESSION_CREATE,
                                  "text_embedding_create_session returned NULL");
    }

    int rc = syms_.init_session(s);
    if (rc != 0) {
        syms_.destroy_session(&s);
        return BridgeStatus::fail(BridgeError::ERR_SESSION_INIT,
                                  "init_session rc=" + std::to_string(rc));
    }

    syms_.enable_event_loop(s, true);
    session_ = s;
    return BridgeStatus::ok(std::monostate{});
}

BridgeStatus EmbeddingBridge::destroy_session() {
    std::lock_guard<std::mutex> lock(mutex_);
    destroy_unlocked();
    return BridgeStatus::ok(std::monostate{});
}

// 私有辅助：调用方须持有锁。释放会话与 .so 句柄，并清零符号表。
void EmbeddingBridge::destroy_unlocked() noexcept {
    if (session_) {
        if (syms_.destroy_session) {
            syms_.destroy_session(&session_);
        } else {
            // 符号缺失时无法正常销毁 SDK 会话对象，记录并接受泄漏
            std::fprintf(stderr,
                         "[Bridge] destroy_unlocked: destroy_session symbol missing, "
                         "session %p leaked\n", static_cast<void*>(session_));
        }
        session_ = nullptr;
    }
    if (handle_) {
        dlclose(handle_);
        handle_ = nullptr;
    }
    // 清零函数指针，防止 dlclose 后访问已卸载 .so 代码段（use-after-dlclose）
    syms_ = EmbeddingSdkSymbols{};
}

BridgeResult<EmbeddingVector> EmbeddingBridge::embed(const std::string& text,
                                                     uint32_t /*timeout_ms*/) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!handle_) {
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_DLOPEN_FAILED,
                                                   "bridge not loaded");
    }
    if (!session_) {
        // 会话未建立：语义上接近 init 未完成，而非 create 动作失败
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_SESSION_INIT,
                                                   "session not created, call create_session() first");
    }

    EmbeddingResult* result = nullptr;
    bool ok = syms_.embed(session_, text.c_str(), &result);
    if (!ok) {
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_EMBED_CALL,
                                                   "text_embedding returned false");
    }
    if (!result) {
        // 调用成功但未填充结果指针：结果读取异常，非调用失败
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_EMBED_RESULT,
                                                   "text_embedding returned true but result is NULL");
    }

    int ec = syms_.result_error_code(result);
    if (ec != 0) {
        // 函数指针与返回值双重判空：SDK 可能在部分错误码下返回空指针
        const char* raw_msg = syms_.result_error_message
                                  ? syms_.result_error_message(result)
                                  : nullptr;
        std::string msg = (raw_msg != nullptr) ? raw_msg : "";
        syms_.result_destroy(&result);
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_EMBED_ERROR,
                                                   "SDK errorCode=" + std::to_string(ec) + " " + msg);
    }

    int dim = syms_.result_vector_length(result);
    float* data = syms_.result_vector_data(result);

    EmbeddingVector vec;
    vec.dimension = dim;
    vec.error_code = 0;
    if (data && dim > 0) {
        vec.data.assign(data, data + dim);
        double sum = 0.0;
        for (float v : vec.data) sum += (double)v * (double)v;
        vec.l2_norm = std::sqrt(sum);
    }

    syms_.result_destroy(&result);
    return BridgeResult<EmbeddingVector>::ok(std::move(vec));
}

} // namespace kylin
