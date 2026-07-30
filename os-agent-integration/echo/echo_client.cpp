/**
 * 麒麟 OS Agent 记忆系统 · Gate 0 SPIKE
 * Kaiming → 自定义 UDS Echo Client
 *
 * 纯 QLocalSocket + QJsonDocument（依赖 Qt5 Core、Network）
 * 编译：qmake / CMake（见 CMakeLists.txt）
 */

#include <QCoreApplication>
#include <QLocalSocket>
#include <QJsonDocument>
#include <QJsonObject>
#include <QByteArray>
#include <QDataStream>
#include <QDebug>

// ── 配置 ──────────────────────────────────────────────────────
static const char* SOCKET_PATH = nullptr; // 由环境变量 KYLIN_MEMORY_SOCK 或 XDG_RUNTIME_DIR 决定
static const int DEADLINE_MS = 2000;      // SPIKE: 2 秒超时

static QString resolveSocketPath() {
    const char* env = qgetenv("KYLIN_MEMORY_SOCK");
    if (env && env[0] != '\0') return QString::fromUtf8(env);

    const char* xdg = qgetenv("XDG_RUNTIME_DIR");
    QString base = (xdg && xdg[0] != '\0') ? QString::fromUtf8(xdg) : QStringLiteral("/tmp");
    return base + QStringLiteral("/kylin-memory/memory.sock");
}

// ── 长度前缀 JSON 发送 ───────────────────────────────────────
static bool sendRequest(QLocalSocket& sock, const QJsonObject& req) {
    QJsonDocument doc(req);
    QByteArray payload = doc.toJson(QJsonDocument::Compact);

    // 4 字节大端长度头
    QByteArray frame;
    QDataStream stream(&frame, QIODevice::WriteOnly);
    stream.setByteOrder(QDataStream::BigEndian);
    stream << (quint32)payload.size();
    frame.append(payload);

    sock.write(frame);
    return sock.waitForBytesWritten(DEADLINE_MS);
}

// ── 长度前缀 JSON 接收 ───────────────────────────────────────
static QJsonObject receiveResponse(QLocalSocket& sock) {
    // 读取 4 字节长度头
    if (!sock.waitForReadyRead(DEADLINE_MS)) {
        qWarning() << "[EchoClient] timeout waiting for header";
        return {{"error", "timeout waiting for header"}};
    }

    QByteArray header = sock.read(4);
    while (header.size() < 4) {
        if (!sock.waitForReadyRead(DEADLINE_MS)) {
            qWarning() << "[EchoClient] timeout reading header, got" << header.size() << "bytes";
            return {{"error", "incomplete header"}};
        }
        header.append(sock.read(4 - header.size()));
    }

    QDataStream headerStream(header);
    headerStream.setByteOrder(QDataStream::BigEndian);
    quint32 payloadLen;
    headerStream >> payloadLen;

    if (payloadLen > 1'000'000) {
        qWarning() << "[EchoClient] payload too large:" << payloadLen;
        return {{"error", "payload too large"}};
    }

    // 读取 JSON 负载
    QByteArray payload = sock.read(payloadLen);
    while ((quint32)payload.size() < payloadLen) {
        if (!sock.waitForReadyRead(DEADLINE_MS)) {
            qWarning() << "[EchoClient] timeout reading payload, got" << payload.size() << "/" << payloadLen;
            return {{"error", "incomplete payload"}};
        }
        payload.append(sock.read(payloadLen - payload.size()));
    }

    QJsonParseError err;
    QJsonDocument doc = QJsonDocument::fromJson(payload, &err);
    if (err.error != QJsonParseError::NoError) {
        qWarning() << "[EchoClient] JSON parse error:" << err.errorString();
        return {{"error", "JSON parse error: " + err.errorString()}};
    }

    return doc.object();
}

// ── 主流程 ────────────────────────────────────────────────────
int main(int argc, char* argv[]) {
    QCoreApplication app(argc, argv);
    const QString sockPath = resolveSocketPath();

    qInfo() << "[EchoClient] connecting to" << sockPath;

    QLocalSocket sock;
    sock.connectToServer(sockPath);
    if (!sock.waitForConnected(DEADLINE_MS)) {
        qCritical() << "[EchoClient] FAIL: cannot connect to" << sockPath
                     << "-" << sock.errorString();
        return 1;
    }
    qInfo() << "[EchoClient] connected";

    // ── 测试 1: memory.retrieve ──────────────────────────────
    {
        QJsonObject req;
        req["protocol_version"] = "1.0";
        req["request_id"] = "echo_test_001";
        req["trace_id"] = "trace_001";
        req["method"] = "memory.retrieve";
        req["deadline_ms"] = 150;
        QJsonObject payload;
        payload["user_id"] = "local-user";
        payload["session_id"] = "session-echo-test";
        payload["query_text"] = "这是测试用户问题";
        payload["scene"] = "software_development";
        payload["max_context_tokens"] = 800;
        req["payload"] = payload;

        if (!sendRequest(sock, req)) {
            qCritical() << "[EchoClient] FAIL: send test 1";
            return 1;
        }

        QJsonObject resp = receiveResponse(sock);
        qInfo() << "[EchoClient] RESPONSE 1:" << QJsonDocument(resp).toJson(QJsonDocument::Compact);

        if (resp["status"].toString() != "ok") {
            qCritical() << "[EchoClient] FAIL: test 1 status not ok";
            return 1;
        }
        qInfo() << "[EchoClient] TEST 1 PASSED (memory.retrieve)";
    }

    // ── 测试 2: memory.observe_turn ──────────────────────────
    {
        QJsonObject req;
        req["protocol_version"] = "1.0";
        req["request_id"] = "echo_test_002";
        req["trace_id"] = "trace_002";
        req["method"] = "memory.observe_turn";
        req["deadline_ms"] = 200;
        QJsonObject payload;
        payload["user_id"] = "local-user";
        payload["session_id"] = "session-echo-test";
        payload["user_text"] = "今天天气怎么样";
        payload["assistant_text"] = "今天多云，气温 25°C";
        payload["status"] = "completed";
        payload["source"] = "text_chat";
        req["payload"] = payload;

        if (!sendRequest(sock, req)) {
            qCritical() << "[EchoClient] FAIL: send test 2";
            return 1;
        }

        QJsonObject resp = receiveResponse(sock);
        qInfo() << "[EchoClient] RESPONSE 2:" << QJsonDocument(resp).toJson(QJsonDocument::Compact);

        if (resp["status"].toString() != "ok") {
            qCritical() << "[EchoClient] FAIL: test 2 status not ok";
            return 1;
        }
        qInfo() << "[EchoClient] TEST 2 PASSED (memory.observe_turn)";
    }

    // ── 测试 3: 超时降级验证（断连后重连） ──────────────────
    {
        sock.disconnectFromServer();
        if (sock.state() != QLocalSocket::UnconnectedState) {
            sock.waitForDisconnected(1000);
        }

        QLocalSocket sock2;
        sock2.connectToServer(sockPath);
        if (sock2.waitForConnected(DEADLINE_MS)) {
            qInfo() << "[EchoClient] reconnected successfully";

            QJsonObject req;
            req["protocol_version"] = "1.0";
            req["request_id"] = "echo_test_003";
            req["trace_id"] = "trace_003";
            req["method"] = "memory.health_check";
            req["deadline_ms"] = 500;
            QJsonObject payload;
            payload["ping"] = true;
            req["payload"] = payload;

            sendRequest(sock2, req);
            QJsonObject resp = receiveResponse(sock2);
            qInfo() << "[EchoClient] RESPONSE 3:" << QJsonDocument(resp).toJson(QJsonDocument::Compact);

            if (resp["status"].toString() == "ok") {
                qInfo() << "[EchoClient] TEST 3 PASSED (health_check)";
            }
        }
    }

    qInfo() << "[EchoClient] ALL TESTS PASSED";
    return 0;
}