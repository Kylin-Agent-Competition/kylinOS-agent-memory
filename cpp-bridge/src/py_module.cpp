/**
 * py_module.cpp
 *
 * 轨道 A — pybind11 绑定模块
 *
 * 将 EmbeddingBridge 暴露给 Python，并把 BridgeError 映射为 Python 异常。
 *
 * 异常映射约定（与 bridge_error_contract.h 错误码对应）：
 *   ERR_SO_NOT_FOUND     → BridgeSoNotFoundError
 *   ERR_DLOPEN_FAILED    → BridgeLoadError
 *   ERR_DLSYM_FAILED     → BridgeSymbolError
 *   ERR_SESSION_*        → BridgeSessionError
 *   ERR_EMBED_CALL       → BridgeEmbedError
 *   ERR_EMBED_RESULT     → BridgeEmbedError
 *   ERR_EMBED_ERROR      → BridgeSdkError
 *   ERR_TIMEOUT          → BridgeTimeoutError
 *   ERR_CANCELLED        → BridgeCancelledError
 *   ERR_MODEL_*          → BridgeModelError
 *   UNKNOWN/NOT_IMPLEMENTED → BridgeError（基类）
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <stdexcept>
#include <string>

#include "embedding_bridge.h"

namespace py = pybind11;
using namespace kylin;

namespace {

// ── C++ 异常类型（pybind11 自动翻译为 Python 异常） ──

struct BridgeErrorException : std::runtime_error {
    using std::runtime_error::runtime_error;
};
struct BridgeSoNotFoundError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };
struct BridgeLoadError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };
struct BridgeSymbolError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };
struct BridgeSessionError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };
struct BridgeEmbedError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };
struct BridgeSdkError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };
struct BridgeTimeoutError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };
struct BridgeCancelledError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };
struct BridgeModelError : BridgeErrorException { using BridgeErrorException::BridgeErrorException; };

// ── BridgeError 枚举 → C++ 异常 映射 ──

[[noreturn]] void raise_for_error(const BridgeError& err, const std::string& msg) {
    switch (err) {
        case BridgeError::ERR_SO_NOT_FOUND:
            throw BridgeSoNotFoundError(msg);
        case BridgeError::ERR_DLOPEN_FAILED:
            throw BridgeLoadError(msg);
        case BridgeError::ERR_DLSYM_FAILED:
            throw BridgeSymbolError(msg);
        case BridgeError::ERR_SESSION_CREATE:
        case BridgeError::ERR_SESSION_INIT:
        case BridgeError::ERR_SESSION_DESTROY:
        case BridgeError::ERR_SESSION_DESTROYED:
            throw BridgeSessionError(msg);
        case BridgeError::ERR_EMBED_CALL:
        case BridgeError::ERR_EMBED_RESULT:
            throw BridgeEmbedError(msg);
        case BridgeError::ERR_EMBED_ERROR:
            throw BridgeSdkError(msg);
        case BridgeError::ERR_TIMEOUT:
            throw BridgeTimeoutError(msg);
        case BridgeError::ERR_CANCELLED:
            throw BridgeCancelledError(msg);
        case BridgeError::ERR_MODEL_NOT_LOADED:
        case BridgeError::ERR_MODEL_INVALID:
            throw BridgeModelError(msg);
        case BridgeError::SUCCESS:
            // 调用方 bug：不应以 SUCCESS 调用 raise_for_error。
            // 抛内部一致性异常（由 pybind11 转为 Python 异常），不终止进程（P1-3）。
            throw BridgeErrorException("internal error: raise_for_error called with SUCCESS");
        case BridgeError::NOT_IMPLEMENTED:
            throw BridgeErrorException("NOT_IMPLEMENTED: " + msg);
        case BridgeError::UNKNOWN:
            throw BridgeErrorException("UNKNOWN: " + msg);
        default:
            throw BridgeErrorException("unknown error: " + msg);
    }
}

} // namespace

PYBIND11_MODULE(kylin_embedding, m) {
    m.doc() = "KylinOS Embedding Bridge (pybind11)";

    // ── 异常注册（继承层次：所有子类继承 BridgeError） ──
    auto bridge_err = py::register_exception<BridgeErrorException>(m, "BridgeError");
    py::register_exception<BridgeSoNotFoundError>(m, "BridgeSoNotFoundError", bridge_err.ptr());
    py::register_exception<BridgeLoadError>(m, "BridgeLoadError", bridge_err.ptr());
    py::register_exception<BridgeSymbolError>(m, "BridgeSymbolError", bridge_err.ptr());
    py::register_exception<BridgeSessionError>(m, "BridgeSessionError", bridge_err.ptr());
    py::register_exception<BridgeEmbedError>(m, "BridgeEmbedError", bridge_err.ptr());
    py::register_exception<BridgeSdkError>(m, "BridgeSdkError", bridge_err.ptr());
    py::register_exception<BridgeTimeoutError>(m, "BridgeTimeoutError", bridge_err.ptr());
    py::register_exception<BridgeCancelledError>(m, "BridgeCancelledError", bridge_err.ptr());
    py::register_exception<BridgeModelError>(m, "BridgeModelError", bridge_err.ptr());


    // ── EmbeddingVector 数据结构 ──

    py::class_<EmbeddingVector>(m, "EmbeddingVector")
        .def_readonly("dimension", &EmbeddingVector::dimension)
        .def_readonly("data", &EmbeddingVector::data)
        .def_readonly("l2_norm", &EmbeddingVector::l2_norm)
        .def("__len__", [](const EmbeddingVector& v) { return v.dimension; })
        .def("__repr__", [](const EmbeddingVector& v) {
            return "<EmbeddingVector dim=" + std::to_string(v.dimension) + ">";
        });

    // ── BridgeInitParams ──

    py::class_<BridgeInitParams>(m, "BridgeInitParams")
        .def(py::init<>())
        .def_readwrite("so_path", &BridgeInitParams::so_path);

    // ── EmbeddingBridge ──

    py::class_<EmbeddingBridge>(m, "EmbeddingBridge")
        .def(py::init<const BridgeInitParams&>(), py::arg("params") = BridgeInitParams{})
        .def("load", [](EmbeddingBridge& b) {
            auto r = b.load();
            if (r.is_fail()) raise_for_error(r.error, r.error_message);
        })
        .def("create_session", [](EmbeddingBridge& b) {
            auto r = b.create_session();
            if (r.is_fail()) raise_for_error(r.error, r.error_message);
        })
        .def("destroy_session", [](EmbeddingBridge& b) {
            auto r = b.destroy_session();
            if (r.is_fail()) raise_for_error(r.error, r.error_message);
        })
        .def("embed", [](EmbeddingBridge& b, const std::string& text, uint32_t timeout_ms) {
            auto r = b.embed(text, timeout_ms);
            if (r.is_fail()) raise_for_error(r.error, r.error_message);
            return *r.value;
        }, py::arg("text"), py::arg("timeout_ms") = 0)
        .def_property_readonly("loaded", &EmbeddingBridge::is_loaded)
        .def_property_readonly("has_session", &EmbeddingBridge::has_session)
        .def_property_readonly("session_destroyed", &EmbeddingBridge::session_destroyed);
}
