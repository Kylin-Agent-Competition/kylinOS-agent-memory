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

    // D5-C 便捷方法：memory.store 请求，用于写入 Post-Turn 观察事件
    // （TurnFinalizedEvent / ToolExecutionEvent 等）。payload 由调用方按契约构造。
    Q_INVOKABLE QString sendMemoryStoreRequest(const QJsonObject& payload);

    // D5-C 便捷方法：发送 TurnFinalizedEvent（Post-Turn 观察）。
    // eventJson 必须符合 os-agent-integration/contracts 中 TurnFinalizedEvent 契约。
    Q_INVOKABLE QString sendTurnFinalizedEvent(const QJsonObject& eventJson);

    // D5-C 便捷方法：发送 ToolExecutionEvent。
    Q_INVOKABLE QString sendToolExecutionEvent(const QJsonObject& eventJson);

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

    QString socketPath_;
    ConnectionState connectionState_ = ConnectionState::Disconnected;
    QString lastError_;

    QPointer<QLocalSocket> socket_;
    QByteArray receiveBuffer_;

    // request_id -> method（用于响应关联与诊断）。本骨架不依赖服务端回传 request_id，
    // 但保留映射以便 L1 联调时验证关联正确性。
    std::unordered_map<std::string, QString> pendingRequests_;
};

}  // namespace kylin::memory::client::v1
