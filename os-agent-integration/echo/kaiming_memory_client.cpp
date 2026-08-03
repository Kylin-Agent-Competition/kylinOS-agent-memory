/**
 * Kaiming Memory Client — 模拟 kylin-aiassistant 宿主进程的 UDS 客户端
 * ======================================================================
 * 模拟真实 Kaiming 宿主进程 (kylin-aiassistant) 发出的标准 Memory Service 请求。
 * 支持 method: echo / health / memory.retrieve / memory.store
 *
 * 用途: Gate 0 P1-1 — 补齐 Kaiming→UDS 端到端链路证据
 * 协议: 4字节 Big-Endian 长度 + UTF-8 JSON 负载
 *
 * 编译 (麒麟 VM):
 *   g++ -std=c++17 -O2 kaiming_memory_client.cpp -o kaiming_memory_client
 *
 * 用法:
 *   ./kaiming_memory_client [--method echo|health|memory.retrieve|memory.store] [--message "text"] [--socket /path/to/sock]
 *
 * 退出码:
 *   0 — 全部测试通过
 *   1 — 部分或全部失败
 */

#include <iostream>
#include <sstream>
#include <string>
#include <cstring>
#include <chrono>
#include <iomanip>
#include <vector>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <arpa/inet.h>

static std::string g_socket_path = "/tmp/kylin-memory-echo/echo.sock";
static int g_pass = 0;
static int g_fail = 0;

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

void log_result(const std::string& test_id, bool passed, const std::string& detail) {
    if (passed) {
        g_pass++;
        std::cout << "RESULT " << test_id << " PASS — " << detail << std::endl;
    } else {
        g_fail++;
        std::cout << "RESULT " << test_id << " FAIL — " << detail << std::endl;
    }
}

/**
 * 通过 POSIX UDS 发送长度前缀 JSON 请求并接收响应
 * 返回 JSON 响应字符串，失败则抛异常
 */
std::string uds_send_recv(const std::string& request_json) {
    int sock = socket(AF_UNIX, SOCK_STREAM, 0);
    if (sock < 0) {
        throw std::runtime_error(std::string("socket() failed: ") + strerror(errno));
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, g_socket_path.c_str(), sizeof(addr.sun_path) - 1);

    if (connect(sock, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        std::string err = std::string("connect() failed: ") + strerror(errno);
        close(sock);
        throw std::runtime_error(err);
    }

    // 发送: 4字节 Big-Endian 长度 + JSON 负载
    uint32_t body_len = htonl(static_cast<uint32_t>(request_json.size()));
    if (send(sock, &body_len, 4, 0) != 4) {
        close(sock);
        throw std::runtime_error("send(header) failed");
    }
    if (send(sock, request_json.c_str(), request_json.size(), 0) != static_cast<ssize_t>(request_json.size())) {
        close(sock);
        throw std::runtime_error("send(body) failed");
    }

    // 接收: 4字节长度 + JSON 负载
    uint32_t resp_len_raw = 0;
    ssize_t n = recv(sock, &resp_len_raw, 4, MSG_WAITALL);
    if (n != 4) {
        close(sock);
        throw std::runtime_error("recv(header) failed or incomplete");
    }
    uint32_t resp_len = ntohl(resp_len_raw);
    if (resp_len == 0 || resp_len > 65536) {
        close(sock);
        throw std::runtime_error("Invalid response length: " + std::to_string(resp_len));
    }

    std::vector<char> resp_buf(resp_len + 1, 0);
    n = recv(sock, resp_buf.data(), resp_len, MSG_WAITALL);
    if (n != static_cast<ssize_t>(resp_len)) {
        close(sock);
        throw std::runtime_error("recv(body) failed or incomplete");
    }
    std::string response_json(resp_buf.data(), resp_len);
    close(sock);
    return response_json;
}

std::string build_request(const std::string& method, const std::string& message) {
    std::ostringstream oss;
    oss << "{"
        << "\"protocol_version\":\"1.0\","
        << "\"request_id\":\"kaiming_req_001\","
        << "\"trace_id\":\"kaiming_trc_001\","
        << "\"method\":\"" << method << "\","
        << "\"deadline_ms\":5000,"
        << "\"payload\":{\"message\":\"" << message << "\"}"
        << "}";
    return oss.str();
}

std::string build_memory_store_request(const std::string& key, const std::string& content) {
    std::ostringstream oss;
    oss << "{"
        << "\"protocol_version\":\"1.0\","
        << "\"request_id\":\"kaiming_store_001\","
        << "\"trace_id\":\"kaiming_trc_store\","
        << "\"method\":\"memory.store\","
        << "\"deadline_ms\":5000,"
        << "\"payload\":{"
        << "\"key\":\"" << key << "\","
        << "\"content\":\"" << content << "\","
        << "\"metadata\":{\"source\":\"kaiming-aiassistant\",\"priority\":\"high\"}"
        << "}}";
    return oss.str();
}

// ---- 测试用例 ----

void test_echo() {
    log_info("TEST: echo 方法");
    try {
        std::string req = build_request("echo", "Hello from Kaiming AI Assistant");
        std::string resp = uds_send_recv(req);
        log_info("Response: " + resp);
        // 简单检查包含 ok 状态和 echo 字段
        bool ok = resp.find("\"status\":\"ok\"") != std::string::npos;
        ok = ok && resp.find("\"echo\":") != std::string::npos;
        log_result("KAIMING-ECHO", ok, "echo 往返, payload=Hello from Kaiming AI Assistant");
    } catch (const std::exception& e) {
        log_error(std::string("Exception: ") + e.what());
        log_result("KAIMING-ECHO", false, std::string("异常: ") + e.what());
    }
}

void test_health() {
    log_info("TEST: health 方法");
    try {
        std::string req = build_request("health", "");
        std::string resp = uds_send_recv(req);
        log_info("Response: " + resp);
        bool ok = resp.find("\"status\":\"ok\"") != std::string::npos;
        ok = ok && resp.find("\"healthy\"") != std::string::npos;
        log_result("KAIMING-HEALTH", ok, "health 查询返回 healthy");
    } catch (const std::exception& e) {
        log_error(std::string("Exception: ") + e.what());
        log_result("KAIMING-HEALTH", false, std::string("异常: ") + e.what());
    }
}

void test_memory_retrieve() {
    log_info("TEST: memory.retrieve 方法");
    try {
        std::string req = build_request("memory.retrieve", "麒麟操作系统安全策略配置");
        std::string resp = uds_send_recv(req);
        log_info("Response: " + resp);
        bool ok = resp.find("\"status\":\"ok\"") != std::string::npos;
        ok = ok && resp.find("\"contexts\"") != std::string::npos;
        ok = ok && resp.find("\"fallback\"") != std::string::npos;
        log_result("KAIMING-RETRIEVE", ok, "memory.retrieve 返回空上下文 (Echo 模拟)");
    } catch (const std::exception& e) {
        log_error(std::string("Exception: ") + e.what());
        log_result("KAIMING-RETRIEVE", false, std::string("异常: ") + e.what());
    }
}

void test_memory_store() {
    log_info("TEST: memory.store 方法 (验证协议兼容性)");
    try {
        // memory.store 不在 Echo 服务端的 METHOD_ROUTER 中，
        // 预期返回 status=error (未知方法降级)
        std::string req = build_memory_store_request("kysec_policy_v1", "最小权限原则: 仅授权进程可访问 UDS socket");
        std::string resp = uds_send_recv(req);
        log_info("Response: " + resp);
        // 当前 Echo 服务端未实现 memory.store，预期 error 响应
        // 但连接本身应成功 (协议层OK)
        bool connected_ok = resp.find("\"status\"") != std::string::npos;
        log_result("KAIMING-STORE", connected_ok, "memory.store 协议层连通 (Echo未实现,预期error)");
    } catch (const std::exception& e) {
        log_error(std::string("Exception: ") + e.what());
        log_result("KAIMING-STORE", false, std::string("协议层异常: ") + e.what());
    }
}

void test_unknown_method() {
    log_info("TEST: 未知方法降级");
    try {
        std::string req = build_request("kaiming.custom.analyze", "test");
        std::string resp = uds_send_recv(req);
        log_info("Response: " + resp);
        bool ok = resp.find("\"status\":\"error\"") != std::string::npos;
        log_result("KAIMING-UNKNOWN", ok, "未知方法返回 status=error (降级正常)");
    } catch (const std::exception& e) {
        log_error(std::string("Exception: ") + e.what());
        log_result("KAIMING-UNKNOWN", false, std::string("异常: ") + e.what());
    }
}

void test_rapid_fire() {
    log_info("TEST: 连续 5 次快速请求 (模拟高频调用)");
    int rapid_pass = 0;
    for (int i = 1; i <= 5; i++) {
        try {
            std::ostringstream msg;
            msg << "RapidFire_" << i;
            std::string req = build_request("echo", msg.str());
            std::string resp = uds_send_recv(req);
            if (resp.find("\"status\":\"ok\"") != std::string::npos) {
                rapid_pass++;
            }
        } catch (const std::exception& e) {
            log_error(std::string("Rapid fire #") + std::to_string(i) + " failed: " + e.what());
        }
    }
    log_result("KAIMING-RAPID", rapid_pass == 5, std::to_string(rapid_pass) + "/5 次快速请求成功");
}

int main(int argc, char* argv[]) {
    std::string method = "all";
    std::string message = "Hello from Kaiming AI Assistant";
    std::string socket_path = "/tmp/kylin-memory-echo/echo.sock";

    // 参数解析
    for (int i = 1; i < argc; i++) {
        std::string arg(argv[i]);
        if (arg == "--method" && i + 1 < argc) {
            method = argv[++i];
        } else if (arg == "--message" && i + 1 < argc) {
            message = argv[++i];
        } else if (arg == "--socket" && i + 1 < argc) {
            socket_path = argv[++i];
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: " << argv[0] << " [--method all|echo|health|memory.retrieve|memory.store] [--message \"text\"] [--socket /path/to/sock]" << std::endl;
            return 0;
        }
    }

    g_socket_path = socket_path;

    std::cout << "============================================" << std::endl;
    std::cout << " Kaiming Memory Client — UDS 端到端验证" << std::endl;
    std::cout << "============================================" << std::endl;
    std::cout << "  模拟进程: kylin-aiassistant (Kaiming 宿主)" << std::endl;
    std::cout << "  Socket: " << g_socket_path << std::endl;
    std::cout << "  Method: " << method << std::endl;
    std::cout << "  用户: " << getenv("USER") << std::endl;
    std::cout << "  UID: " << getuid() << std::endl;
    std::cout << "============================================" << std::endl;

    if (method == "echo") {
        test_echo();
    } else if (method == "health") {
        test_health();
    } else if (method == "memory.retrieve") {
        test_memory_retrieve();
    } else if (method == "memory.store") {
        test_memory_store();
    } else if (method == "all") {
        test_echo();
        test_health();
        test_memory_retrieve();
        test_memory_store();
        test_unknown_method();
        test_rapid_fire();
    } else {
        std::cerr << "Unknown method: " << method << std::endl;
        return 1;
    }

    std::cout << std::endl;
    std::cout << "============================================" << std::endl;
    std::cout << " 测试汇总" << std::endl;
    std::cout << "============================================" << std::endl;
    std::cout << "  通过: " << g_pass << std::endl;
    std::cout << "  失败: " << g_fail << std::endl;
    std::cout << "============================================" << std::endl;

    return g_fail > 0 ? 1 : 0;
}