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
    // 析构时释放会话与 .so 句柄（进程级单例场景：进程退出时卸载）。
    // 不加锁：析构时不应有并发访问；调用方应在析构前先 destroy_session()。
    destroy_unlocked();
}

BridgeStatus EmbeddingBridge::load() {
    try {
        return load_impl();
    } catch (const std::bad_alloc&) {
        return BridgeStatus::fail(BridgeError::UNKNOWN, "load: bad_alloc");
    } catch (const std::exception& e) {
        return BridgeStatus::fail(BridgeError::UNKNOWN, std::string("load: ") + e.what());
    } catch (...) {
        return BridgeStatus::fail(BridgeError::UNKNOWN, "load: unknown exception");
    }
}

BridgeStatus EmbeddingBridge::load_impl() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (fatal_failure_) {
        // P1-High: 不可恢复失败（已 dlclose），禁止重试 dlopen
        return BridgeStatus::fail(BridgeError::ERR_FATAL_FAILURE,
                                  "fatal failure, restart required");
    }
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
        // P1-High: 已执行 dlclose，置 fatal（同进程 dlclose→dlopen 可能 Abort）。
        // P1-1(R2): 首次失败保留原始原因 ERR_DLSYM_FAILED（Day3 契约：dlsym 失败
        // → Provider ERR_SDK_NOT_LOADED）；fatal 后重试才返回 ERR_FATAL_FAILURE。
        fatal_failure_ = true;
        return BridgeStatus::fail(BridgeError::ERR_DLSYM_FAILED,
                                  "required symbol missing from " + params_.so_path
                                  + " (fatal: dlclose 已执行，不可重试)");
    }

    syms_ = tmp;  // 全部验证后一次性赋值
    handle_ = h;
    return BridgeStatus::ok(std::monostate{});
}

BridgeStatus EmbeddingBridge::create_session() {
    try {
        return create_session_impl();
    } catch (const std::bad_alloc&) {
        return BridgeStatus::fail(BridgeError::UNKNOWN, "create_session: bad_alloc");
    } catch (const std::exception& e) {
        return BridgeStatus::fail(BridgeError::UNKNOWN,
                                  std::string("create_session: ") + e.what());
    } catch (...) {
        return BridgeStatus::fail(BridgeError::UNKNOWN, "create_session: unknown exception");
    }
}

BridgeStatus EmbeddingBridge::create_session_impl() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (fatal_failure_) {
        // P1-High: 不可恢复失败（已 dlclose/destroy），禁止重试
        return BridgeStatus::fail(BridgeError::ERR_FATAL_FAILURE,
                                  "fatal failure, restart required");
    }
    if (!handle_) {
        return BridgeStatus::fail(BridgeError::ERR_DLOPEN_FAILED, "bridge not loaded");
    }
    if (session_destroyed_) {
        // P0-2: destroy 后不可恢复终态，禁止重建（宿主会挂起）
        return BridgeStatus::fail(BridgeError::ERR_SESSION_DESTROYED,
                                  "session destroyed, cannot recreate (SDK 不允许同进程重建)");
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
        // P1-High: 已执行 destroy_session，置 fatal（同进程 destroy→create 可能挂起）。
        // P1-1(R2): 首次失败保留原始原因 ERR_SESSION_INIT（Day3 契约：init_session
        // 失败 → Provider ERR_SESSION_FAILED）；fatal 后重试才返回 ERR_FATAL_FAILURE。
        fatal_failure_ = true;
        return BridgeStatus::fail(BridgeError::ERR_SESSION_INIT,
                                  "init_session rc=" + std::to_string(rc)
                                  + " (fatal: destroy 已执行，不可重试)");
    }

    syms_.enable_event_loop(s, true);
    session_ = s;
    return BridgeStatus::ok(std::monostate{});
}

BridgeStatus EmbeddingBridge::destroy_session() {
    try {
        return destroy_session_impl();
    } catch (const std::bad_alloc&) {
        return BridgeStatus::fail(BridgeError::UNKNOWN, "destroy_session: bad_alloc");
    } catch (const std::exception& e) {
        return BridgeStatus::fail(BridgeError::UNKNOWN,
                                  std::string("destroy_session: ") + e.what());
    } catch (...) {
        return BridgeStatus::fail(BridgeError::UNKNOWN, "destroy_session: unknown exception");
    }
}

BridgeStatus EmbeddingBridge::destroy_session_impl() {
    std::lock_guard<std::mutex> lock(mutex_);
    // 只销毁会话；保留 .so 句柄（P0-1 生命周期修复）。
    // SDK 动态库在进程生命周期内只加载一次，不执行 dlclose()：
    // 麒麟实测 dlclose 后再次 dlopen 会触发 Fatal Python error: Aborted。
    if (session_) {
        if (syms_.destroy_session) {
            syms_.destroy_session(&session_);
        } else {
            // 符号缺失时无法正常销毁 SDK 会话对象，记录并接受泄漏
            std::fprintf(stderr,
                         "[Bridge] destroy_session: destroy_session symbol missing, "
                         "session %p leaked\n", static_cast<void*>(session_));
        }
        session_ = nullptr;
    }
    // P0-2: 置终态标志——销毁后不可重建（SDK 不允许同进程 destroy→create）
    session_destroyed_ = true;
    // NOTE: 不执行 dlclose(handle_)，保留已解析符号。
    // 真正卸载 .so 在析构函数 destroy_unlocked() 中进行（进程退出/单例销毁时）。
    return BridgeStatus::ok(std::monostate{});
}

// 私有辅助：调用方须持有锁。释放会话与 .so 句柄，并清零符号表。
// 仅在析构函数中调用（进程级单例销毁/进程退出时）；
// destroy_session() 不卸载 .so（P0-1 生命周期修复）。
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
    try {
        return embed_impl(text);
    } catch (const std::bad_alloc&) {
        return BridgeResult<EmbeddingVector>::fail(BridgeError::UNKNOWN,
                                                   "embed: bad_alloc");
    } catch (const std::exception& e) {
        return BridgeResult<EmbeddingVector>::fail(BridgeError::UNKNOWN,
                                                   std::string("embed: ") + e.what());
    } catch (...) {
        return BridgeResult<EmbeddingVector>::fail(BridgeError::UNKNOWN,
                                                   "embed: unknown exception");
    }
}

// 实际实现（无异常边界，由 embed() 包裹）
BridgeResult<EmbeddingVector> EmbeddingBridge::embed_impl(const std::string& text) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (fatal_failure_) {
        // P1-High: 不可恢复失败，禁止重试
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_FATAL_FAILURE,
                                                   "fatal failure, restart required");
    }
    if (!handle_) {
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_DLOPEN_FAILED,
                                                   "bridge not loaded");
    }
    if (session_destroyed_) {
        // P0-2: 销毁后终态，embed 稳定报错（不挂起）
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_SESSION_DESTROYED,
                                                   "session destroyed, cannot embed");
    }
    if (!session_) {
        // 会话未建立：语义上接近 init 未完成，而非 create 动作失败
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_SESSION_INIT,
                                                   "session not created, call create_session() first");
    }

    // RAII Guard：确保任何返回路径都释放 SDK 结果对象（P0-3）
    struct ResultGuard {
        EmbeddingResult** ptr;
        void (*destroy)(EmbeddingResult**);
        ~ResultGuard() {
            if (*ptr && destroy) destroy(ptr);
        }
    };

    EmbeddingResult* result = nullptr;
    bool ok = syms_.embed(session_, text.c_str(), &result);
    ResultGuard guard{&result, syms_.result_destroy};
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
        return BridgeResult<EmbeddingVector>::fail(BridgeError::ERR_EMBED_ERROR,
                                                   "SDK errorCode=" + std::to_string(ec) + " " + msg);
    }

    int dim = syms_.result_vector_length(result);
    float* data = syms_.result_vector_data(result);

    // 畸形结果防御（P0-2）：返回成功前必须验证结果有效性
    if (dim <= 0) {
        return BridgeResult<EmbeddingVector>::fail(
            BridgeError::ERR_EMBED_RESULT,
            "invalid dimension: " + std::to_string(dim));
    }
    if (!data) {
        return BridgeResult<EmbeddingVector>::fail(
            BridgeError::ERR_EMBED_RESULT,
            "vector data is NULL");
    }

    EmbeddingVector vec;
    vec.dimension = dim;
    vec.error_code = 0;
    vec.data.assign(data, data + dim);
    if (vec.data.size() != static_cast<size_t>(dim)) {
        return BridgeResult<EmbeddingVector>::fail(
            BridgeError::ERR_EMBED_RESULT,
            "vector copy size mismatch");
    }

    double sum = 0.0;
    for (float v : vec.data) {
        if (std::isnan(v) || std::isinf(v)) {
            return BridgeResult<EmbeddingVector>::fail(
                BridgeError::ERR_EMBED_RESULT,
                "vector contains NaN/Inf");
        }
        sum += (double)v * (double)v;
    }
    vec.l2_norm = std::sqrt(sum);

    return BridgeResult<EmbeddingVector>::ok(std::move(vec));
}

} // namespace kylin
