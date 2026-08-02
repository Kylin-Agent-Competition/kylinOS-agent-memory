/**
 * Kylin Memory Echo Client — UDS 最小验证客户端
 * ================================================
 * 连接 /tmp/kylin-memory-echo/echo.sock ，发送长度前缀 JSON 请求，
 * 接收响应并输出结果。
 *
 * 用途: Gate 0 验证 Kaiming 进程可通过 UDS 与自定义 Memory Service 通信
 * 协议: 4字节 Big-Endian 长度 + UTF-8 JSON 负载
 *
 * 编译 (麒麟 VM):
 *   g++ -std=c++17 echo_client.cpp -o echo_client
 *   或通过 CMake (需要 Qt5 QLocalSocket)
 *
 * 用法:
 *   ./echo_client [--method echo|health|memory.retrieve] [--message "text"]
 */

#include <iostream>
#include <sstream>
#include <string>
#include <cstring>
#include <chrono>
#include <iomanip>
#include <vector>

#ifdef QLOCALSOCKET_AVAILABLE
#include <QLocalSocket>
#include <QCoreApplication>
#include <QJsonDocument>
#include <QJsonObject>
#endif

// ---- POSIX 实现 (无需 Qt) ----
#ifndef QLOCALSOCKET_AVAILABLE
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <arpa/inet.h>

static std::string g_socket_path = "/tmp/kylin-memory-echo/echo.sock";

std::string now_iso() {
    auto now = std::chrono::system_clock::now();
    auto time_t_now = std::chrono::system_clock::to_time_t(now);
    std::ostringstream oss;
    oss << std::put_time(std::gmtime(&time_t_now), "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}

void log_info(const std::string& msg) {
    std::cerr << "[" << now_iso() << "] [INFO] " << msg << std::endl;
}

void log_error(const std::string& msg) {
    std::cerr << "[" << now_iso() << "] [ERROR] " << msg << std::endl;
}

/**
 * 通过 POSIX UDS 发送长度前缀 JSON 请求并接收响应
 */
int uds_send_recv(const std::string& request_json) {
    int sock = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sock < 0) {
        log_error("socket() failed: " + std::string(strerror(errno)));
        return 1;
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, g_socket_path.c_str(), sizeof(addr.sun_path) - 1);

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        log_error("connect() failed: " + std::string(strerror(errno)));
        close(sock);
        return 1;
    }
    log_info("Connected to " + g_socket_path);

    // ---- 发送: 4字节 Big-Endian 长度 + JSON 负载 ----
    uint32_t body_len = htonl(static_cast<uint32_t>(request_json.size()));
    if (send(sock, &body_len, 4, 0) != 4) {
        log_error("send(header) failed");
        close(sock);
        return 1;
    }
    if (send(sock, request_json.c_str(), request_json.size(), 0) != static_cast<ssize_t>(request_json.size())) {
        log_error("send(body) failed");
        close(sock);
        return 1;
    }
    log_info("Sent " + std::to_string(request_json.size()) + " bytes");

    // ---- 接收: 4字节长度 + JSON 负载 ----
    uint32_t resp_len_raw = 0;
    ssize_t n = recv(sock, &resp_len_raw, 4, MSG_WAITALL);
    if (n != 4) {
        log_error("recv(header) failed or incomplete");
        close(sock);
        return 1;
    }
    uint32_t resp_len = ntohl(resp_len_raw);
    if (resp_len == 0 || resp_len > 65536) {
        log_error("Invalid response length: " + std::to_string(resp_len));
        close(sock);
        return 1;
    }

    std::vector<char> resp_buf(resp_len + 1, 0);
    n = recv(sock, resp_buf.data(), resp_len, MSG_WAITALL);
    if (n != static_cast<ssize_t>(resp_len)) {
        log_error("recv(body) failed or incomplete");
        close(sock);
        return 1;
    }
    std::string response_json(resp_buf.data(), resp_len);
    close(sock);

    std::cout << "=== RESPONSE ===" << std::endl;
    std::cout << response_json << std::endl;
    std::cout << "================" << std::endl;

    log_info("Round-trip OK");
    return 0;
}

std::string build_request(const std::string& method, const std::string& message) {
    std::ostringstream oss;
    oss << "{"
        << "\"protocol_version\":\"1.0\","
        << "\"request_id\":\"req_test_001\","
        << "\"trace_id\":\"trc_test_001\","
        << "\"method\":\"" << method << "\","
        << "\"deadline_ms\":5000,"
        << "\"payload\":{\"message\":\"" << message << "\"}"
        << "}";
    return oss.str();
}

int main(int argc, char* argv[]) {
    std::string method = "echo";
    std::string message = "Hello from Kylin Echo Client";
    std::string socket_path = "/tmp/kylin-memory-echo/echo.sock";

    // 简单参数解析
    for (int i = 1; i < argc; i++) {
        std::string arg(argv[i]);
        if (arg == "--method" && i + 1 < argc) {
            method = argv[++i];
        } else if (arg == "--message" && i + 1 < argc) {
            message = argv[++i];
        } else if (arg == "--socket" && i + 1 < argc) {
            socket_path = argv[++i];
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: " << argv[0] << " [--method echo|health|memory.retrieve] [--message \"text\"] [--socket /path/to/sock]" << std::endl;
            return 0;
        }
    }

    g_socket_path = socket_path;

    log_info("Echo Client starting");
    log_info("  Socket: " + g_socket_path);
    log_info("  Method: " + method);
    log_info("  Message: " + message);

    std::string request = build_request(method, message);
    log_info("Request: " + request);

    int rc = uds_send_recv(request);
    return rc;
}
#else
// Qt 实现占位 (如需 QLocalSocket)
int main(int argc, char* argv[]) {
    std::cerr << "QLocalSocket backend not yet implemented. Use POSIX build." << std::endl;
    return 1;
}
#endif