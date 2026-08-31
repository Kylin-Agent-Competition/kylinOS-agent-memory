#pragma once

#include <QLocalSocket>
#include <QObject>
#include <QPointer>
#include <QString>

#include <optional>
#include <unordered_map>

#include "protocol_adapter.h"

namespace kylin::memory::client::v1 {

// ============================================================================
// MemoryClient — Qt/QML 侧记忆客户端
// ============================================================================
//
// 状态：L0 骨架（Mock 契约测试通过）；L1 QLocalSocket 连接 Memory Service 待联调；
// L2 麒麟 VM 真实链路未实现。
//
// 职责：
//   - 通过 QLocalSocket 连接 Memory Service（UDS on Linux / named pipe on Windows）
//   - 异步发送/接收长度前缀 JSON envelope（D 轨 IPC 候选）
//   - 提供 QML 友好的 Q_INVOKABLE 接口与信号
//   - 不直接操作 SQLite/Vector；不修改官方 AI 助手 UI 源码
//
// 设计要点：
//   - 单请求/响应模型：sendRequest() 返回 request_id，responseReceived 信号带
//     匹配的 request_id（envelope 原样回传则关联成功）
//   - 不阻塞 UI 线程：所有 I/O 异步，信号驱动
//   - 错误信号固定安全消息，不回显用户正文或凭据
//   - 协议错误直接复用 ProtocolError（不发明新错误模型）
//
// 未实现（明确不在本骨架内）：
//   - 重连退避、重试、超时取消（待 D 轨 IPC 终审后引入）
//   - 真实 MemoryContext 注入（受 docs/day3/11 §10 BLOCKED 阻断）
//   - 偏好/知识 CRUD（待 E 轨业务 Schema 终审后接入）
// ============================================================================

class MemoryClient : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString socketPath READ socketPath WRITE setSocketPath
                   NOTIFY socketPathChanged)
    Q_PROPERTY(ConnectionState connectionState READ connectionState
                   NOTIFY connectionStateChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)

public:
    enum class ConnectionState {
        Disconnected,
        Connecting,
        Connected,
        Closing,
    };
    Q_ENUM(ConnectionState)

    explicit MemoryClient(QObject* parent = nullptr);
    ~MemoryClient() override;

    MemoryClient(const MemoryClient&) = delete;
    MemoryClient& operator=(const MemoryClient&) = delete;

    [[nodiscard]] QString socketPath() const { return socketPath_; }
    void setSocketPath(const QString& path);

    [[nodiscard]] ConnectionState connectionState() const { return connectionState_; }
    [[nodiscard]] QString lastError() const { return lastError_; }

    // 连接 Memory Service。异步：连接成功/失败通过 connectionStateChanged 信号回报。
    // 重复调用在已连接时为 no-op。
    Q_INVOKABLE void connectToService();

    // 主动断开。in-flight 请求以 requestFailed 报错（ERR_CONNECTION_CLOSING）。
    Q_INVOKABLE void disconnectFromService();

    // 发送请求 envelope。返回生成的 request_id；空串表示发送失败（未连接或
    // 编码失败）。响应通过 responseReceived 信号回报，request_id 与本返回值匹配。
    // 注意：method/payload 由调用方构造；本客户端不做业务校验（契约校验在
    // os-agent-integration/contracts 已实现）。
    Q_INVOKABLE QString sendRequest(const QString& method, const QJsonObject& payload);

    // 便捷方法：memory.health 请求，无 payload。
    Q_INVOKABLE QString sendHealthRequest();

    // D5-C 便捷方法：memory.store 请求（记忆条目写入骨架）。
    // ⚠️  D 轨 FRZ-IPC-007 持续返回 UNSUPPORTED_METHOD（ADR-010 §决策明确
    //     memory.store 保持未实现，不动）。仅保留常量 / 入口方便对比测试。
    Q_INVOKABLE QString sendMemoryStoreRequest(const QJsonObject& payload);

    // D5-C 便捷方法：发送 TurnFinalizedEvent（Post-Turn 写链路 Demo）。
    // 路由：turn.finalized（ADR-010 冻结；CANDIDATE / BLOCKED_BY_HOST_MAPPING；
    // 生产默认不注册；Demo/测试可注册）。
    // payload = eventJson，字段严格对齐 ADR-010 IPC 映射契约：
    //   metadata{schema_version,event_id,user_id,session_id,turn_id,
    //     idempotency_key,trace_id?,occurred_at,collected_at,source_reference}
    //   事件(is_final,finalized_at,final_message_id?,finalization_reason?,
    //     stop_reason?,retry_of_turn_id?,tool_call_ids?)
    // ADR-010 trace_id 唯一真源：envelope.trace_id 取 metadata.trace_id
    // （若提供）；不再使用旧 {event_type,event_body} wrapper。
    Q_INVOKABLE QString sendTurnFinalizedEvent(const QJsonObject& eventJson);

    // ── D6-C 多源 Adapter 写链路 Demo（候选方法，不冻结） ───────────────
    // 三个候选写方法均沿用 ADR-010 模式：生产 Gateway 默认不注册 → 返回
    // UNSUPPORTED_METHOD；测试态可显式注入 handler。
    //
    // 1) tool.execution：对齐 ToolExecutionEvent v1（D3 已冻结）。
    //    payload = eventJson，字段对齐 contracts/examples/tool_execution_event.v1.json
    //    + metadata{schema_version,event_id,user_id,session_id,turn_id,
    //      idempotency_key,trace_id?,occurred_at,collected_at,source_reference}
    //    trace_id 唯一真源：envelope.trace_id 取 metadata.trace_id（若提供）。
    Q_INVOKABLE QString sendToolExecutionEvent(const QJsonObject& eventJson);

    // 2) manual.config.ingest：候选 schema（contracts/examples/manual_config_event.v1.json）。
    //    payload = eventJson，候选字段：
    //      metadata{...同上}
    //      config{scope,key,value,is_temporary,should_persist,confidence?,
    //             source_reference}
    //    ViewModel 客户端侧预检敏感内容；high/critical 敏感等级不发送到 Gateway。
    Q_INVOKABLE QString sendManualConfigEvent(const QJsonObject& eventJson);

    // 3) behavior.observe：候选 schema（contracts/examples/behavior_event.v1.json）。
    //    payload = eventJson，候选字段：
    //      metadata{...同上}
    //      behavior{behavior_kind,observed_action,context_ref,actor,occurred_at,
    //               mapping_status="PENDING_C_CONFIRMATION"}
    //    behavior → MemorySourceEvent.source_type 映射未冻结；
    //    ViewModel 在事件 JSON 中显式注入 mapping_status 字段。
    Q_INVOKABLE QString sendBehaviorEvent(const QJsonObject& eventJson);

    // ── D7-C 偏好版本管理写链路 Demo（候选方法，不冻结） ──────────────────
    // 三个候选方法沿用 ADR-010 / D6-C 模式：生产 Gateway 默认不注册 →
    // UNSUPPORTED_METHOD；测试态可显式注入 handler。
    //
    // 1) preference.version.commit：对齐 D7D save_preference_version。
    //    payload = eventJson，候选字段：
    //      metadata{schema_version,event_id,user_id,session_id,turn_id,
    //        idempotency_key,trace_id?,occurred_at,collected_at,source_reference}
    //      preference{user_id,key,scope,value,memory_status,is_temporary,
    //        should_persist,confidence?,sensitivity_level,mapping_status=
    //        "PENDING_C_CONFIRMATION"}
    //    trace_id 唯一真源：envelope.trace_id 取 metadata.trace_id（若提供）。
    Q_INVOKABLE QString sendPreferenceCommitEvent(const QJsonObject& eventJson);

    // 2) preference.version.history：对齐 D7D list_preference_versions。
    //    payload = eventJson，候选字段：
    //      metadata{...同上}
    //      query{user_id,key,scope,include_history}
    Q_INVOKABLE QString sendPreferenceHistoryRequest(const QJsonObject& eventJson);

    // 3) preference.version.rollback：对齐 D7D rollback_preference_version。
    //    payload = eventJson，候选字段：
    //      metadata{...同上}
    //      rollback{user_id,key,scope,target_version_id,idempotency_key?}
    Q_INVOKABLE QString sendPreferenceRollbackEvent(const QJsonObject& eventJson);

signals:
    void socketPathChanged();
    void connectionStateChanged();
    void lastErrorChanged();

    // 收到完整响应 envelope。requestId 为请求时返回值（envelope 原样回传则匹配）。
    void responseReceived(const QString& requestId, const QJsonObject& envelope);

    // 单个请求失败（协议错误、连接关闭、编码失败等）。errorCode 为 ProtocolErrorKind
    // 对应的固定安全消息，不含原文。
    void requestFailed(const QString& requestId, const QString& errorCode, const QString& safeMessage);

    // 连接级错误（不含 requestId）。
    void connectionError(const QString& safeMessage);

private slots:
    void handleSocketConnected();
    void handleSocketDisconnected();
    void handleSocketErrorOccurred(QLocalSocket::LocalSocketError error);
    void handleSocketReadyRead();

private:
    void setConnectionState(ConnectionState state);
    void setLastError(const QString& message);
    void failInFlightRequests(const QString& errorCode, const QString& safeMessage);
    QString generateRequestId() const;

    // D6-C / D7-C 共享写链路：构造 envelope（trace_id 取 metadata.trace_id 若提供，
    // 否则回退 request_id）→ 编码 → 写入 socket → 注册 pending。
    // 失败时 emit requestFailed 并返回空串；成功返回 request_id。
    // 供 sendTurnFinalizedEvent / sendToolExecutionEvent /
    //     sendManualConfigEvent / sendBehaviorEvent /
    //     sendPreferenceCommitEvent / sendPreferenceHistoryRequest /
    //     sendPreferenceRollbackEvent 复用。
    QString sendEventEnvelope(const QString& method, const QJsonObject& eventJson);

    QString socketPath_;
    ConnectionState connectionState_ = ConnectionState::Disconnected;
    QString lastError_;

    QPointer<QLocalSocket> socket_;
    QByteArray receiveBuffer_;

    // request_id -> {method, trace_id}（用于响应关联与 trace_id 一致性校验）。
    struct PendingRequest {
        QString method;
        QString traceId;
    };
    std::unordered_map<std::string, PendingRequest> pendingRequests_;
};

}  // namespace kylin::memory::client::v1
