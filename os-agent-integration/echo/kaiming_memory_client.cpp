/**
 * Kaiming Memory Client - Simulated kylin-aiassistant Host Process UDS Client
 * ===========================================================================
 * Simulates standard Memory Service requests from a real Kaiming host process
 * (kylin-aiassistant). Supports methods: echo / health / memory.retrieve / memory.store
 *
 * Purpose: Gate 0 P1-1 - Complete Kaiming-to-UDS end-to-end link evidence
 * Protocol: 4-byte Big-Endian length + UTF-8 JSON payload
 *
 * Build (Kylin VM):
 *   g++ -std=c++17 -O2 kaiming_memory_client.cpp -o kaiming_memory_client
 *
 * Exit code: 0 = all passed, 1 = failures present
 */

#include <iostream>
#include <sstream>
#include <string>
#include <cerrno>
#include <cstring>
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

// Extract "status" field value from JSON string (whitespace-independent)
// Expected format: ..."status": "ok"... or ..."status": "error"...
static std::string extract_json_status(const std::string& json) {
    auto pos = json.find("\"status\"");
    if (pos == std::string::npos) return "";
    // Skip "status"
    pos += 8;
    // Find first quote after colon
    auto q1 = json.find('"', json.find(':', pos));
    if (q1 == std::string::npos) return "";
    auto q2 = json.find('"', q1 + 1);
    if (q2 == std::string::npos) return "";
    return json.substr(q1 + 1, q2 - q1 - 1);
}

// Check if a key exists in JSON (whitespace-independent)
static bool json_has_key(const std::string& json, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    return json.find(pattern) != std::string::npos;
}

// Extract a string value for a given key from JSON (whitespace-independent)
// e.g. extract_json_string_value(json, "error_code") returns "UNSUPPORTED_METHOD"
static std::string extract_json_string_value(const std::string& json, const std::string& key) {
    std::string pattern = "\"" + key + "\"";
    auto pos = json.find(pattern);
    if (pos == std::string::npos) return "";
    pos += pattern.length();
    // Skip whitespace and colon
    auto colon = json.find(':', pos);
    if (colon == std::string::npos) return "";
    auto q1 = json.find('"', colon);
    if (q1 == std::string::npos) return "";
    auto q2 = json.find('"', q1 + 1);
    if (q2 == std::string::npos) return "";
    return json.substr(q1 + 1, q2 - q1 - 1);
}

// UDS send/receive
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
        << "}"
        << "}";
    return oss.str();
}

// ---- Test Cases ----

void test_echo() {
    log_info("TEST: echo method");
    try {
        std::string resp = uds_send_recv(build_request("echo", "Hello from Kaiming AI Assistant"));
        log_info("Response: " + resp);
        bool ok = (extract_json_status(resp) == "ok") && json_has_key(resp, "echo");
        log_result("KAIMING-ECHO", ok, "echo roundtrip payload=Hello from Kaiming AI Assistant");
    } catch (const std::exception& e) {
        log_result("KAIMING-ECHO", false, std::string("exception: ") + e.what());
    }
}

void test_health() {
    log_info("TEST: health method");
    try {
        std::string resp = uds_send_recv(build_request("health", ""));
        log_info("Response: " + resp);
        bool ok = (extract_json_status(resp) == "ok") && json_has_key(resp, "healthy");
        log_result("KAIMING-HEALTH", ok, "health query returned healthy");
    } catch (const std::exception& e) {
        log_result("KAIMING-HEALTH", false, std::string("exception: ") + e.what());
    }
}

void test_memory_retrieve() {
    log_info("TEST: memory.retrieve method");
    try {
        std::string resp = uds_send_recv(build_request("memory.retrieve", "Kylin OS security policy config"));
        log_info("Response: " + resp);
        bool ok = (extract_json_status(resp) == "ok")
               && json_has_key(resp, "contexts")
               && json_has_key(resp, "fallback");
        log_result("KAIMING-RETRIEVE", ok, "memory.retrieve returned empty context (Echo simulation)");
    } catch (const std::exception& e) {
        log_result("KAIMING-RETRIEVE", false, std::string("exception: ") + e.what());
    }
}

void test_memory_store() {
    log_info("TEST: memory.store method (verify protocol compatibility)");
    try {
        std::string resp = uds_send_recv(build_memory_store_request("kysec_policy_v1", "least privilege principle"));
        log_info("Response: " + resp);
        // Echo does not implement memory.store; expected:
        //   status=="error" AND error_code=="UNSUPPORTED_METHOD" AND message present
        // PROTOCOL_ERROR / INTERNAL_ERROR / parse failures / missing error_code value -> FAIL
        bool ok = (extract_json_status(resp) == "error")
               && (extract_json_string_value(resp, "error_code") == "UNSUPPORTED_METHOD")
               && json_has_key(resp, "message");
        log_result("KAIMING-STORE", ok, "memory.store correctly returned status=error with error_code=UNSUPPORTED_METHOD (Echo not implemented)");
    } catch (const std::exception& e) {
        log_result("KAIMING-STORE", false, std::string("protocol layer exception: ") + e.what());
    }
}

void test_unknown_method() {
    log_info("TEST: unknown method degradation");
    try {
        std::string resp = uds_send_recv(build_request("kaiming.custom.analyze", "test"));
        log_info("Response: " + resp);
        bool ok = (extract_json_status(resp) == "error");
        log_result("KAIMING-UNKNOWN", ok, "unknown method returned status=error (degradation normal)");
    } catch (const std::exception& e) {
        log_result("KAIMING-UNKNOWN", false, std::string("exception: ") + e.what());
    }
}

void test_rapid_fire() {
    log_info("TEST: 5 consecutive rapid requests (simulating high-frequency calls)");
    int ok_count = 0;
    for (int i = 1; i <= 5; i++) {
        try {
            std::string resp = uds_send_recv(build_request("echo", "RapidFire_" + std::to_string(i)));
            if (extract_json_status(resp) == "ok") ok_count++;
        } catch (const std::exception& e) {
            log_error(std::string("Rapid #") + std::to_string(i) + ": " + e.what());
        }
    }
    log_result("KAIMING-RAPID", ok_count == 5, std::to_string(ok_count) + "/5 rapid requests succeeded");
}

// ---- Main Entry ----
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
    std::cout << " Kaiming Memory Client - v1.3 (value-aware)" << std::endl;
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
    std::cout << " Passed: " << g_pass << " / Failed: " << g_fail << std::endl;
    std::cout << "============================================" << std::endl;
    return g_fail > 0 ? 1 : 0;
}