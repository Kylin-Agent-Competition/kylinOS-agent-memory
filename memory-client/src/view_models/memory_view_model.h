#pragma once

#include <QJsonObject>
#include <QObject>
#include <QString>
#include <QVariantList>

#include "memory_client.h"

namespace kylin::memory::client::v1 {

// ============================================================================
// MemoryViewModel — QML 公共 ViewModel
// ============================================================================
//
// 状态：L0 骨架；不承载真实业务语义（偏好/知识 Schema 未冻结）。
//
// 职责：
//   - 包装 MemoryClient，向 QML 暴露 Q_PROPERTY 绑定（状态/最近响应/错误）
//   - 提供 Q_INVOKABLE 触发动作（连接、断开、健康检查、查询）
//   - 把 MemoryClient 的信号聚合成 QML 可直接绑定的属性变化
//
// 边界：
//   - 不解析 MemoryContext 业务字段（待 E 轨 Schema 终审）
//   - 不内嵌用户正文或凭据（只承载契约 JSON 对象）
//   - 不替代 PreferenceEditor/ForgetPlan 等专用 ViewModel（后续按轨道引入）
// ============================================================================

class MemoryViewModel : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString socketPath READ socketPath WRITE setSocketPath
                   NOTIFY socketPathChanged)
    Q_PROPERTY(QString connectionState READ connectionState
                   NOTIFY connectionStateChanged)
    Q_PROPERTY(QString lastError READ lastError NOTIFY lastErrorChanged)
    Q_PROPERTY(QString lastRequestId READ lastRequestId NOTIFY lastRequestIdChanged)
    Q_PROPERTY(QJsonObject lastResponse READ lastResponse NOTIFY lastResponseChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)

public:
    explicit MemoryViewModel(QObject* parent = nullptr);
    ~MemoryViewModel() override;

    MemoryViewModel(const MemoryViewModel&) = delete;
    MemoryViewModel& operator=(const MemoryViewModel&) = delete;

    [[nodiscard]] QString socketPath() const;
    void setSocketPath(const QString& path);

    [[nodiscard]] QString connectionState() const;
    [[nodiscard]] QString lastError() const;
    [[nodiscard]] QString lastRequestId() const { return lastRequestId_; }
    [[nodiscard]] QJsonObject lastResponse() const { return lastResponse_; }
    [[nodiscard]] bool busy() const { return busy_; }

    // QML 可调用动作。
    Q_INVOKABLE void connectToService();
    Q_INVOKABLE void disconnectFromService();
    Q_INVOKABLE void sendHealth();
    // 发送 memory.query 请求。payload 由调用方构造，本骨架不做业务校验。
    Q_INVOKABLE void sendMemoryQuery(const QJsonObject& payload);

signals:
    void socketPathChanged();
    void connectionStateChanged();
    void lastErrorChanged();
    void lastRequestIdChanged();
    void lastResponseChanged();
    void busyChanged();

    // 请求失败时向 QML 报告固定安全消息（不含原文）。
    void requestFailed(const QString& requestId, const QString& errorCode, const QString& safeMessage);

private slots:
    void onConnectionStateChanged();
    void onLastErrorChanged();
    void onResponseReceived(const QString& requestId, const QJsonObject& envelope);
    void onRequestFailed(const QString& requestId, const QString& errorCode, const QString& safeMessage);
    void onConnectionError(const QString& safeMessage);

private:
    void setBusy(bool value);
    void setLastRequestId(const QString& id);
    void setLastResponse(const QJsonObject& envelope);

    MemoryClient client_;
    QString lastRequestId_;
    QJsonObject lastResponse_;
    bool busy_ = false;
};

}  // namespace kylin::memory::client::v1
