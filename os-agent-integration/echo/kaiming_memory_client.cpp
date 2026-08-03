/**
 * Kaiming Memory Client �?模拟 kylin-aiassistant 宿主进程�?UDS 客户�? * ======================================================================
 * 模拟真实 Kaiming 宿主进程 (kylin-aiassistant) 发出的标�?Memory Service 请求�? * 支持 method: echo / health / memory.retrieve / memory.store
 *
 * 用�? Gate 0 P1-1 �?补齐 Kaiming→UDS 端到端链路证�? * 协议: 4字节 Big-Endian 长度 + UTF-8 JSON 负载
 *
 * 编译 (麒麟 VM):
 *   g++ -std=c++17 -O2 kaiming_memory_client.cpp -o kaiming_memory_client
 *
 * 退出码: 0 �?全部通过, 1 �?有失�? */

#include <iostream>
#include <sstream>
#include <string>
#include <cerrno>`n#include <cstring>
#include <chrono>
#include <iomanip>
#include <vector>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <arpa/inet.h>

static std::string g_socket_path = "/run/kylin-memory-echo/echo.sock";
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
        std::cout << "RESULT " << test_id << " PASS" << std::endl;
        log_info(test_id + " PASS: " + detail);
    } else {
        g_fail++;
        std::cout << "RESULT " << test_id << " FAIL" << std::endl;
        log_info(test_id + " FAIL: " + detail);
    }
}

// �?JSON 字符串中提取 "status" 字段的�?(不依赖空�?
// 预期格式: ..."status": "ok"... �?..."status": "error"...
static std::string extract_json_status(const std::string& json) {
    auto pos = json.find("\"status\"");
    if (pos == std::string::npos) return "";
    // 跳过 "status"
    pos += 8;
    // 找冒号后的第一个引�?    auto q1 = json.find('"', json.find(':', pos));
    if (q1 == std::string::npos) return "";
    auto q2 = json.find('"', q1 + 1);
    if (q2 == std::string::npos) return "";
    return json.substr(q1 + 1, q2 - q1 - 1);
}

// 检�?JSON 中某�?key 是否存在 (不依赖空�?
static bool json_has_key(const std::string& json, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    return json.find(pattern) != std::string::npos;
}

// UDS 收发
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
        close(sock);
        throw std::runtime_error(std::string("connect() failed: ") + strerror(errno));
    }
    uint32_t body_len = htonl(static_cast<uint32_t>(request_json.size()));
    send(sock, &body_len, 4, 0);
    send(sock, request_json.c_str(), request_json.size(), 0);
    uint32_t resp_len_raw = 0;
    recv(sock, &resp_len_raw, 4, MSG_WAITALL);
    uint32_t resp_len = ntohl(resp_len_raw);
    if (resp_len == 0 || resp_len > 65536) {
        close(sock);
        throw std::runtime_error("Invalid response length");
    }
    std::vector<char> buf(resp_len + 1, 0);
    recv(sock, buf.data(), resp_len, MSG_WAITALL);
    std::string resp(buf.data(), resp_len);
    close(sock);
    return resp;
}

std::string build_request(const std::string& method, const std::string& message) {
    std::ostringstream oss;
    oss << "{"
        << R"("protocol_version":"1.0",)"
        << R"("request_id":"kaiming_req_001",)"
        << R"("trace_id":"kaiming_trc_001",)"
        << R"("method":")" << method << R"(",)"
        << R"("deadline_ms":5000,)"
        << R"("payload":{"message":")" << message << "\"}"
        << "}";
    return oss.str();
}

std::string build_memory_store_request(const std::string& key, const std::string& content) {
    std::ostringstream oss;
    oss << "{"
        << R"("protocol_version":"1.0",)"
        << R"("request_id":"kaiming_store_001",)"
        << R"("trace_id":"kaiming_trc_store",)"
        << R"("method":"memory.store",)"
        << R"("deadline_ms":5000,)"
        << R"("payload":{)"
        << R"("key":")" << key << R"(",)"
        << R"("content":")" << content << R"(",)"
        << R"("metadata":{"source":"kaiming-aiassistant","priority":"high"})"
        << "}";
    return oss.str();
}

// ---- 测试用例 ----

void test_echo() {
    log_info("TEST: echo 方法");
    try {
        std::string resp = uds_send_recv(build_request("echo", "Hello from Kaiming AI Assistant"));
        log_info("Response: " + resp);
        bool ok = (extract_json_status(resp) == "ok") && json_has_key(resp, "echo");
        log_result("KAIMING-ECHO", ok, "echo 往�? payload=Hello from Kaiming AI Assistant");
    } catch (const std::exception& e) {
        log_result("KAIMING-ECHO", false, std::string("异常: ") + e.what());
    }
}

void test_health() {
    log_info("TEST: health 方法");
    try {
        std::string resp = uds_send_recv(build_request("health", ""));
        log_info("Response: " + resp);
        bool ok = (extract_json_status(resp) == "ok") && json_has_key(resp, "healthy");
        log_result("KAIMING-HEALTH", ok, "health 查询返回 healthy");
    } catch (const std::exception& e) {
        log_result("KAIMING-HEALTH", false, std::string("异常: ") + e.what());
    }
}

void test_memory_retrieve() {
    log_info("TEST: memory.retrieve 方法");
    try {
        std::string resp = uds_send_recv(build_request("memory.retrieve", "麒麟操作系统安全策略配置"));
        log_info("Response: " + resp);
        bool ok = (extract_json_status(resp) == "ok")
               && json_has_key(resp, "contexts")
               && json_has_key(resp, "fallback");
        log_result("KAIMING-RETRIEVE", ok, "memory.retrieve 返回空上下文 (Echo 模拟)");
    } catch (const std::exception& e) {
        log_result("KAIMING-RETRIEVE", false, std::string("异常: ") + e.what());
    }
}

void test_memory_store() {
    log_info("TEST: memory.store 方法 (验证协议兼容�?");
    try {
        std::string resp = uds_send_recv(build_memory_store_request("kysec_policy_v1", "最小权限原�?));
        log_info("Response: " + resp);
        // Echo 未实�?memory.store, 预期 error
        bool ok = json_has_key(resp, "status");
        log_result("KAIMING-STORE", ok, "memory.store 协议层连�?(Echo未实�?预期error)");
    } catch (const std::exception& e) {
        log_result("KAIMING-STORE", false, std::string("协议层异�? ") + e.what());
    }
}

void test_unknown_method() {
    log_info("TEST: 未知方法降级");
    try {
        std::string resp = uds_send_recv(build_request("kaiming.custom.analyze", "test"));
        log_info("Response: " + resp);
        bool ok = (extract_json_status(resp) == "error");
        log_result("KAIMING-UNKNOWN", ok, "未知方法返回 status=error (降级正常)");
    } catch (const std::exception& e) {
        log_result("KAIMING-UNKNOWN", false, std::string("异常: ") + e.what());
    }
}

void test_rapid_fire() {
    log_info("TEST: 连续 5 次快速请�?(模拟高频调用)");
    int ok_count = 0;
    for (int i = 1; i <= 5; i++) {
        try {
            std::string resp = uds_send_recv(build_request("echo", "RapidFire_" + std::to_string(i)));
            if (extract_json_status(resp) == "ok") ok_count++;
        } catch (const std::exception& e) {
            log_error(std::string("Rapid #") + std::to_string(i) + ": " + e.what());
        }
    }
    log_result("KAIMING-RAPID", ok_count == 5, std::to_string(ok_count) + "/5 次快速请求成�?);
}

// ---- 主入�?----
int main(int argc, char* argv[]) {
    std::string method = "all";
    std::string socket_path = "/tmp/kylin-memory-echo/echo.sock";

    for (int i = 1; i < argc; i++) {
        std::string arg(argv[i]);
        if (arg == "--method" && i + 1 < argc) method = argv[++i];
        else if (arg == "--socket" && i + 1 < argc) socket_path = argv[++i];
        else if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: " << argv[0] << " [--method all|echo|health|memory.retrieve|memory.store] [--socket PATH]" << std::endl;
            return 0;
        }
    }

    g_socket_path = socket_path;

    std::cout << "============================================" << std::endl;
    std::cout << " Kaiming Memory Client �?v1.1 (robust JSON)" << std::endl;
    std::cout << " Socket: " << g_socket_path << std::endl;
    std::cout << " Method: " << method << std::endl;
    std::cout << " User: " << (getenv("USER") ? getenv("USER") : "?") << std::endl;
    std::cout << "============================================" << std::endl;

    if (method == "echo") test_echo();
    else if (method == "health") test_health();
    else if (method == "memory.retrieve") test_memory_retrieve();
    else if (method == "memory.store") test_memory_store();
    else if (method == "all") {
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
    std::cout << " 通过: " << g_pass << " / 失败: " << g_fail << std::endl;
    std::cout << "============================================" << std::endl;
    return g_fail > 0 ? 1 : 0;
}
