/**
 * embedding_bridge.h
 *
 * 轨道 A — Embedding C++ Bridge
 *
 * 基于 embedding_abi_compat.h（ABI 兼容声明）与 bridge_error_contract.h（错误契约）
 * 封装 Embedding SDK 的最小真实调用路径：
 *   dlopen → dlsym → create_session → init_session → text_embedding → 结果读取 → destroy
 *
 * 设计规则：
 * 1. 所有公开方法返回 BridgeResult<T>，不抛出 C++ 异常。
 * 2. 错误码映射见 bridge_error_contract.h。
 * 3. 本文件仅实现 Day4 骨架所需的最小接口（同步 embed + 会话生命周期）。
 */

#ifndef KYLIN_EMBEDDING_BRIDGE_H
#define KYLIN_EMBEDDING_BRIDGE_H

#include "bridge_error_contract.h"
#include "embedding_abi_compat.h"

#include <string>
#include <vector>
#include <memory>
#include <mutex>

namespace kylin {

// ── Embedding 结果（C++ 侧表示） ──

struct EmbeddingVector {
    int dimension = 0;
    std::vector<float> data;
    double l2_norm = 0.0;
    int error_code = 0;
    std::string error_message;
};

// ── 内部：SDK 动态符号表（通过 dlsym 加载） ──

struct EmbeddingSdkSymbols {
    // 会话
    TextEmbeddingSession* (*create_session)(void) = nullptr;
    void (*destroy_session)(TextEmbeddingSession**) = nullptr;
    int  (*init_session)(TextEmbeddingSession*) = nullptr;
    void (*enable_event_loop)(TextEmbeddingSession*, bool) = nullptr;

    // 同步 embedding
    bool (*embed)(TextEmbeddingSession*, const char*, EmbeddingResult**) = nullptr;

    // 结果读取
    float* (*result_vector_data)(EmbeddingResult*) = nullptr;
    int    (*result_vector_length)(EmbeddingResult*) = nullptr;
    int    (*result_error_code)(EmbeddingResult*) = nullptr;
    const char* (*result_error_message)(EmbeddingResult*) = nullptr;
    void   (*result_destroy)(EmbeddingResult**) = nullptr;

    // 模型（可选，Day4 骨架暂不强制）
    int (*init_model)(TextEmbeddingSession*, const char*) = nullptr;

    // [TD-A-005-04 已解决] 模型列表/信息查询（SDK embedding_api.h 声明，nm 确认导出）
    // 用于 model_info() 获取真实模型名（替代硬编码默认模型名）
    EmbeddingModelList* (*get_model_list)(TextEmbeddingSession*, int*) = nullptr;
    int  (*model_list_get_count)(EmbeddingModelList*) = nullptr;
    EmbeddingModelInfo* (*model_list_get_model)(EmbeddingModelList*, int) = nullptr;
    const char* (*model_info_get_model_name)(EmbeddingModelInfo*) = nullptr;
    int  (*model_info_get_model_dim)(EmbeddingModelInfo*) = nullptr;
};

// ── EmbeddingBridge ──

class EmbeddingBridge {
public:
    explicit EmbeddingBridge(const BridgeInitParams& params = BridgeInitParams{});
    ~EmbeddingBridge();

    // 非拷贝非移动
    EmbeddingBridge(const EmbeddingBridge&) = delete;
    EmbeddingBridge& operator=(const EmbeddingBridge&) = delete;

    // ── 生命周期 ──

    /** 加载 .so 并解析符号。重复调用幂等。 */
    BridgeStatus load();

    /** 创建并初始化会话。 */
    BridgeStatus create_session();

    /**
     * 销毁会话。重复调用幂等。
     *
     * 生命周期终态（P0-2）：调用后 Bridge 进入不可恢复终态（session_destroyed_），
     * 再次调用 create_session() 或 embed() 返回稳定错误 ERR_SESSION_DESTROYED。
     * 原因：麒麟实测 SDK 不允许同一进程 destroy_session → create_session
     * （会阻塞挂起整个进程），因此销毁后不得重建。
     * 注意：不卸载 .so；has_session() 返回 false 但 is_loaded() 仍为 true。
     */
    BridgeStatus destroy_session();

    // ── Embedding 调用 ──

    /** 单条文本向量化（同步）。不抛出 C++ 异常，异常在内部捕获转为错误。 */
    BridgeResult<EmbeddingVector> embed(const std::string& text, uint32_t timeout_ms = 0);

    // ── 模型信息（TD-A-005-04） ──

    /**
     * 获取默认模型名（通过 SDK get_model_list 查询真实模型名）。
     * 返回空串表示不可用（符号缺失 / 查询失败 / 无模型）。
     * 不抛异常；失败返回空串（调用方回退硬编码默认名）。
     */
    std::string get_default_model_name();

    // ── 状态查询 ──

    bool is_loaded() const { return handle_ != nullptr; }
    bool has_session() const { return session_ != nullptr; }
    /** 是否已进入销毁终态（destroy_session 后不可再 create_session/embed）。 */
    bool session_destroyed() const { return session_destroyed_; }
    /** 是否已进入不可恢复失败态（dlsym/init_session 失败后已 dlclose/destroy，禁止重试）。 */
    bool fatal_failure() const { return fatal_failure_; }

private:
    BridgeInitParams params_;
    void* handle_ = nullptr;
    EmbeddingSdkSymbols syms_;
    TextEmbeddingSession* session_ = nullptr;
    bool session_destroyed_ = false;  // P0-2: destroy 后终态标志
    bool fatal_failure_ = false;      // P1-High: 不可恢复失败标志（已发生 dlclose/destroy）
    std::mutex mutex_;

    // 私有辅助：仅在析构函数中调用。释放会话与 .so 句柄并清零符号表。
    void destroy_unlocked() noexcept;

    // 无异常边界的实现体，由公共方法 try/catch 包裹（P0-3/P1-5）
    BridgeStatus load_impl();
    BridgeStatus create_session_impl();
    BridgeStatus destroy_session_impl();
    BridgeResult<EmbeddingVector> embed_impl(const std::string& text);
};

} // namespace kylin

#endif // KYLIN_EMBEDDING_BRIDGE_H
