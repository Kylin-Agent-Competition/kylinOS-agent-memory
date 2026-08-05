/**
 * bridge_error_contract.h
 *
 * 轨道 A — C++ Bridge 错误契约 v1
 *
 * 定义 Bridge 层的错误类型、超时、取消和模型状态枚举。
 * 所有 Bridge 接口统一使用此契约中的类型返回状态。
 *
 * 规则：
 * 1. 所有 Bridge 函数返回 BridgeResult<T>，成功含值，失败含错误码+消息。
 * 2. 不抛出 C++ 异常（noexcept），异常在 Bridge 内部捕获并转为错误码。
 * 3. 超时：Day4 未实现主动超时中断（TD-A-005-01 已登记）。timeout_ms 参数
 *    当前无实际效果，仅透传保留；ERR_TIMEOUT 仅在 Day5 实现定时器后产生。
 *    timeout_ms=0 语义未定义（Day4 不保证主动中断，也不保证超时返回）。
 * 4. 取消通过线程安全的状态标志位实现，不强制中断 SDK 内部调用。
 */

#ifndef KYLIN_BRIDGE_ERROR_CONTRACT_H
#define KYLIN_BRIDGE_ERROR_CONTRACT_H

#include <cstdint>
#include <string>
#include <optional>
#include <functional>
#include <atomic>
#include <variant>

// ── 错误码枚举 ──
//
// 错误码分段：
//   0x00xx  通用
//   0x01xx  SDK 加载
//   0x02xx  会话
//   0x03xx  Embedding 调用
//   0x04xx  超时与取消
//   0x05xx  模型状态
//
// 检测顺序（SDK 加载段）：
//   1. 先 access()/stat() 检查 .so 文件存在性 → ERR_SO_NOT_FOUND
//   2. dlopen 失败但文件存在 → ERR_DLOPEN_FAILED
//   3. dlsym 关键符号缺失 → ERR_DLSYM_FAILED

enum class BridgeError : uint32_t {
    // 通用 (0x00xx)
    SUCCESS             = 0x0000,
    UNKNOWN             = 0x0001,
    NOT_IMPLEMENTED     = 0x0002,

    // SDK 加载 (0x01xx)
    ERR_SO_NOT_FOUND    = 0x0101,   // .so 文件不存在（access 检测）
    ERR_DLOPEN_FAILED   = 0x0102,   // dlopen 失败（文件存在但无法加载）
    ERR_DLSYM_FAILED    = 0x0103,   // dlsym 关键符号缺失

    // 会话 (0x02xx)
    ERR_SESSION_CREATE  = 0x0201,   // create_session 返回 NULL
    ERR_SESSION_INIT    = 0x0202,   // init_session 返回非零
    ERR_SESSION_DESTROY = 0x0203,   // destroy_session 异常
    ERR_SESSION_DESTROYED = 0x0204, // 会话已销毁（终态，禁止重建——SDK 不允许同进程 destroy→create，P0-2）

    // Embedding 调用 (0x03xx)
    ERR_EMBED_CALL      = 0x0301,   // text_embedding 返回 false
    ERR_EMBED_RESULT    = 0x0302,   // 结果读取异常
    ERR_EMBED_ERROR     = 0x0303,   // SDK 返回非零 errorCode

    // 超时与取消 (0x04xx)
    ERR_TIMEOUT         = 0x0401,   // 超过内部超时阈值
    ERR_CANCELLED       = 0x0402,   // 被调用方取消

    // 模型状态 (0x05xx)
    ERR_MODEL_NOT_LOADED = 0x0501,  // 模型未加载或加载失败
    ERR_MODEL_INVALID   = 0x0502,   // 指定的模型名不存在
};

// ── 模型状态枚举 ──

enum class ModelState : uint8_t {
    UNKNOWN      = 0,    // 未初始化
    LOADING      = 1,    // 正在加载
    READY        = 2,    // 已加载，可调用
    ERROR        = 3,    // 加载失败或运行时异常
    UNLOADED     = 4,    // 已卸载
};

// ── Bridge 统一返回类型 ──

template <typename T>
struct BridgeResult {
    BridgeError error;
    std::string error_message;
    std::optional<T> value;

    static BridgeResult<T> ok(T val) {
        return { BridgeError::SUCCESS, "", std::move(val) };
    }

    static BridgeResult<T> fail(BridgeError err, const std::string& msg = "") {
        return { err, msg, std::nullopt };
    }

    bool is_ok() const { return error == BridgeError::SUCCESS; }
    bool is_fail() const { return error != BridgeError::SUCCESS; }
};

// 无返回值操作（如 destroy_session）使用 BridgeStatus
using BridgeStatus = BridgeResult<std::monostate>;

// ── 取消标志 ──

/**
 * 线程安全的取消标志。
 * Bridge 在长时间操作中定期检查此标志。
 * 调用方调用 cancel() 后，Bridge 在下一次检查点返回 ERR_CANCELLED。
 */
struct CancelToken {
    virtual bool is_cancelled() const = 0;
    virtual void reset() = 0;
    virtual ~CancelToken() = default;
};

/** 基于 std::atomic_bool 的默认取消标志实现 */
struct AtomicCancelToken final : public CancelToken {
    std::atomic_bool flag{false};

    bool is_cancelled() const override { return flag.load(); }
    void reset() override { flag.store(false); }
    void cancel() { flag.store(true); }
};

// ── 超时配置 ──

struct TimeoutConfig {
    uint32_t embed_ms = 5000;   // 单次向量化超时（毫秒）
    uint32_t batch_ms = 30000;  // 批量向量化超时（毫秒）
    uint32_t init_ms  = 10000;  // 会话初始化超时（毫秒）
};

// ── Bridge 初始化参数 ──

struct BridgeInitParams {
    // 默认 .so 路径按编译架构选择；aarch64 路径为 UNTESTED（无实机证据）
#if defined(__aarch64__)
    std::string so_path = "/usr/lib/aarch64-linux-gnu/libkysdk-coreai-embedding.so.1";  // UNTESTED
#else
    std::string so_path = "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1";  // x86_64 宿主证据 embedding_abi_symbols.log:7
#endif
    // NOTE: 依赖库路径（如 /usr/lib/kylin-ai/depends）由部署期 LD_LIBRARY_PATH 配置，
    // 不作为 BridgeInitParams 字段（P1-2：避免"看似可配置但实际无效"的误导字段）。
    TimeoutConfig timeouts;
};

#endif // KYLIN_BRIDGE_ERROR_CONTRACT_H
