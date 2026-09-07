#pragma once

#include <QLocalSocket>
#include <QObject>
#include <QPointer>
#include <QString>
#include <QTimer>

#include <chrono>
#include <optional>
#include <unordered_map>

#include "protocol_adapter.h"

namespace kylin::memory::client::v1 {

// ============================================================================
// MemoryClient — Qt/QML 侧记忆客户端
// ============================================================================
//
// 状态：D12-C 缺陷清理版（含断线重连、客户端超时、严格协议边界）。
//       L0 Mock 契约测试；L1/L2 联调待验证。
//
// 职责：
//   - 通过 QLocalSocket 连接 Memory Service（UDS on Linux / named pipe on Windows）
//   - 异步发送/接收长度前缀 JSON envelope（D 轨 IPC 冻结 FRZ-IPC-001~007）
//   - 提供 QML 友好的 Q_INVOKABLE 接口与信号
//   - D12-C 新增：自动重连、客户端 deadline 超时取消 pending、严格 parse 边界
//
// 设计要点：
//   - 单请求/响应模型：sendRequest() 返回 request_id，responseReceived 信号带
//     匹配的 request_id（envelope 原样回传则关联成功）
//   - 不阻塞 UI 线程：所有 I/O 异步，信号驱动
//   - 错误信号固定安全消息，不回显用户正文或凭据
//
// D12-C 新增：
//   - TD-IPC-004：3 次指数退避自动重连（可关闭），仅对"意外断开"触发
//   - TD-022：客户端 deadline_ms + 100ms 超时检查；超时后 pendingRequests_
//     同步 expire/cancel，emit requestFailed(TIMEOUT)
//   - 显式 Stop/Retry：disconnectFromService 清除 pending；重连后可重试
// ============================================================================

class MemoryClient : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString socketPath READ socketPath WRITE setSocketPath
                   NOTIFY socketPathChanged)
    Q_PROPERTY(ConnectionState connectionState READ connectionState
                   NOTIFY connectionStateChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)
    // D12-C：重连统计（便于 UI/Demo 展示和测试断言）
    Q_PROPERTY(int reconnectAttempts READ reconnectAttempts
                   NOTIFY reconnectAttemptsChanged)
    Q_PROPERTY(bool autoReconnectEnabled READ autoReconnectEnabled
                   WRITE setAutoReconnectEnabled NOTIFY autoReconnectEnabledChanged)

public:
    enum class ConnectionState {
        Disconnected,
        Connecting,
        Connected,
        Closing,
        Reconnecting,   // D12-C：重连等待中（指数退避计时窗口）
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
    [[nodiscard]] int reconnectAttempts() const { return reconnectAttempts_; }
    [[nodiscard]] bool autoReconnectEnabled() const { return autoReconnectEnabled_; }
    void setAutoReconnectEnabled(bool enabled);

    // D12-C MEDIUM-02：允许覆盖默认 deadline_ms（测试可设短值加速 timing boundary 验证）。
    [[nodiscard]] int deadlineMs() const { return deadlineMs_; }
    void setDeadlineMs(int ms);

    // 连接 Memory Service。异步：连接成功/失败通过 connectionStateChanged 信号回报。
    // 重复调用在已连接时为 no-op。
    Q_INVOKABLE void connectToService();

    // 主动断开（Stop）。in-flight 请求以 requestFailed 报错（ERR_CONNECTION_CLOSING）。
    // D12-C：显式 Stop 不计入"意外断开"，不触发自动重连。
    Q_INVOKABLE void disconnectFromService();

    // D12-C：显式 Retry（调用方决定重连时机）。等价于 disconnect + connect，
    // 但保留 socketPath 且不修改 autoReconnectEnabled。
    Q_INVOKABLE void retryConnect();

    // 发送请求 envelope。返回生成的 request_id；空串表示发送失败（未连接或
    // 编码失败）。响应通过 responseReceived 信号回报，request_id 与本返回值匹配。
    Q_INVOKABLE QString sendRequest(const QString& method, const QJsonObject& payload);

    // 便捷方法：memory.health 请求，无 payload。
    Q_INVOKABLE QString sendHealthRequest();

    // D5-C 便捷方法：memory.store 请求（记忆条目写入骨架）。
    // ⚠️  D 轨 FRZ-IPC-007 持续返回 UNSUPPORTED_METHOD（ADR-010 §决策明确
    //     memory.store 保持未实现，不动）。仅保留常量 / 入口方便对比测试。
    Q_INVOKABLE QString sendMemoryStoreRequest(const QJsonObject& payload);

    // D5-C 便捷方法：发送 TurnFinalizedEvent（Post-Turn 写链路 Demo）。
    Q_INVOKABLE QString sendTurnFinalizedEvent(const QJsonObject& eventJson);

    // D7C 偏好 IPC 便捷方法
    Q_INVOKABLE QString sendPreferenceListRequest(const QJsonObject& payload);
    Q_INVOKABLE QString sendPreferenceCreateRequest(const QJsonObject& payload);
    Q_INVOKABLE QString sendPreferenceUpdateRequest(const QJsonObject& payload);
    Q_INVOKABLE QString sendPreferenceRollbackRequest(const QJsonObject& payload);
    Q_INVOKABLE QString sendPreferenceHistoryRequest(const QJsonObject& payload);

    // D6-C 候选写方法
    Q_INVOKABLE QString sendToolExecutionEvent(const QJsonObject& eventJson);
    Q_INVOKABLE QString sendManualConfigEvent(const QJsonObject& eventJson);
    Q_INVOKABLE QString sendBehaviorEvent(const QJsonObject& eventJson);

    // D8C 候选 IPC 便捷方法
    Q_INVOKABLE QString sendKnowledgeDetailRequest(const QJsonObject& payload);
    Q_INVOKABLE QString sendConflictCompareRequest(const QJsonObject& payload);
    Q_INVOKABLE QString sendLifecycleStatusRequest(const QJsonObject& payload);

    // D9C 候选 IPC 便捷方法
    Q_INVOKABLE QString sendContextAssembleRequest(const QJsonObject& payload);

    // D10C 候选 IPC 便捷方法
    Q_INVOKABLE QString sendForgetPreviewRequest(const QJsonObject& payload);
    Q_INVOKABLE QString sendForgetExecuteRequest(const QJsonObject& payload);

signals:
    void socketPathChanged();
    void connectionStateChanged();
    void lastErrorChanged();
    void reconnectAttemptsChanged();
    void autoReconnectEnabledChanged();

    // 收到完整响应 envelope。
    void responseReceived(const QString& requestId, const QJsonObject& envelope);

    // 单个请求失败（协议错误、连接关闭、超时、编码失败等）。
    void requestFailed(const QString& requestId, const QString& errorCode, const QString& safeMessage);

    // 连接级错误（不含 requestId）。
    void connectionError(const QString& safeMessage);

    // D12-C：重连完成（成功或达到最大次数）。success=true 表示重连后已连接。
    void reconnectFinished(bool success, int attempts);

private slots:
    void handleSocketConnected();
    void handleSocketDisconnected();
    void handleSocketErrorOccurred(QLocalSocket::LocalSocketError error);
    void handleSocketReadyRead();

private:
    void setConnectionState(ConnectionState state);
    void setLastError(const QString& message);
    void setReconnectAttempts(int n);
    void failInFlightRequests(const QString& errorCode, const QString& safeMessage);
    QString generateRequestId() const;

    // D12-C TD-IPC-004：重连辅助
    void startReconnectBackoff();
    void cancelReconnectTimer();

    // D12-C TD-022：客户端级 deadline 超时
    void startClientDeadlineTimer(const QString& requestId, int deadlineMs);
    void cancelClientDeadlineFor(const QString& requestId);
    void expirePendingRequest(const QString& requestId,
                              const QString& errorCode,
                              const QString& safeMessage);

    // 共享写链路
    QString sendEventEnvelope(const QString& method, const QJsonObject& eventJson);

    QString socketPath_;
    ConnectionState connectionState_ = ConnectionState::Disconnected;
    QString lastError_;
    bool autoReconnectEnabled_ = true;     // 默认开启；显式 disconnect 关闭且不触发
    bool manualDisconnectInProgress_ = false;  // Stop 时置 true，避免触发自动重连
    bool protocolFatalDisconnect_ = false;     // D12-C MEDIUM-01：协议错误 abort 后置 true，抑制后续 disconnected 信号的 auto-reconnect
    int reconnectAttempts_ = 0;
    int maxReconnectAttempts_ = 3;        // TD-IPC-004：3 次指数退避
    int deadlineMs_ = 5000;               // D12-C MEDIUM-02：可覆盖 deadline_ms（测试加速）
    std::chrono::milliseconds reconnectBaseDelay_{500};  // 初始延迟 500ms（2^0*500）
    QPointer<QTimer> reconnectTimer_;

    QPointer<QLocalSocket> socket_;
    QByteArray receiveBuffer_;

    // request_id -> PendingRequest（含 deadline wall-clock 截止时间戳 ms）。
    struct PendingRequest {
        QString method;
        QString traceId;
        qint64 deadlineEpochMs = 0;  // TD-022：绝对截止时间（QDateTime::currentMSecsSinceEpoch）
    };
    std::unordered_map<std::string, PendingRequest> pendingRequests_;
    // request_id -> QTimer（客户端超时取消）
    std::unordered_map<std::string, QPointer<QTimer>> clientDeadlineTimers_;
};

}  // namespace kylin::memory::client::v1
