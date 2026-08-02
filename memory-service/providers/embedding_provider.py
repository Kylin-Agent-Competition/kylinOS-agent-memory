"""
embedding_provider.py

轨道 A — EmbeddingProvider v1（Day4 骨架）

基于 pybind11 模块 kylin_embedding 封装 EmbeddingBridge，
对外提供 Day3 冻结的 Provider 接口：
  - embed(text, timeout_ms) -> EmbeddingResult
  - embed_batch(texts, timeout_ms) -> list[EmbeddingResult]
  - get_dimension() -> int
  - model_info() -> ModelInfo

状态：骨架已建立。embed 路径在麒麟 VM 实测（Day2 证据），
embed_batch 为应用层批处理（顺序调用），get_dimension/model_info 依赖 SDK 接口。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

try:
    import kylin_embedding as _bridge
except ImportError as exc:  # pragma: no cover - 骨架阶段未编译时给出明确提示
    _bridge = None
    _IMPORT_ERROR = f"kylin_embedding 模块不可用: {exc}. 请先在麒麟 VM 用 CMake 构建 pybind11 模块。"
else:
    _IMPORT_ERROR = None


# ── Provider 级错误码（Day3 契约冻结） ──

class ProviderErrorCode(IntEnum):
    """Provider 层错误码，与 Day3 06_provider_contract_v1.md 一致。"""

    ERR_SDK_NOT_LOADED = 0x0101  # dlopen/dlsym 失败（Bridge ERR_SO/DLOPEN/DLSYM）
    ERR_SESSION_FAILED = 0x0201  # create/init 会话失败（Bridge ERR_SESSION_*）
    ERR_EMBED_FAILED = 0x0301    # text_embedding 返回 false（Bridge ERR_EMBED_CALL）
    ERR_SDK_ERROR = 0x0303       # SDK 返回非零 errorCode（Bridge ERR_EMBED_ERROR）
    ERR_TIMEOUT = 0x0401         # 超过 timeout_ms（Bridge ERR_TIMEOUT）
    ERR_INVALID_TEXT = 0x0500    # text 非 str 类型（应用层校验，不进 Bridge）
    ERR_UNKNOWN = 0x0001         # 未分类错误


class ProviderError(Exception):
    """Provider 层统一异常：隐藏 Bridge 底层细节（P1-1）。"""

    def __init__(self, code: ProviderErrorCode, message: str, *, bridge_error: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.bridge_error = bridge_error  # 原始 Bridge 错误码（诊断用）

    def __str__(self) -> str:
        return f"[{self.code.name}] {self.message}"


@dataclass
class EmbeddingResult:
    """单条文本向量化结果（与 Day3 契约一致）。"""

    vector: List[float]
    dimension: int
    l2_norm: float
    error_code: int = 0
    error_message: Optional[str] = None

    def __len__(self) -> int:
        return self.dimension


@dataclass
class ModelInfo:
    """当前模型元信息（ondevice 标注 ASSUMED，见 Day3 契约）。"""

    name: str
    dimension: int
    ondevice: bool = True  # ASSUMED: 未经 SDK API 验证
    loaded: bool = False


class EmbeddingProvider:
    """
    Embedding 向量化服务（骨架）。
    每次调用通过 C++ Bridge 走 dlopen → dlsym → text_embedding 路径。
    """

    # Bridge 异常 → Provider 错误码映射（P1-1：隐藏 Bridge 细节）
    _BRIDGE_ERROR_MAP = {
        "BridgeSoNotFoundError": ProviderErrorCode.ERR_SDK_NOT_LOADED,
        "BridgeLoadError": ProviderErrorCode.ERR_SDK_NOT_LOADED,
        "BridgeSymbolError": ProviderErrorCode.ERR_SDK_NOT_LOADED,
        "BridgeSessionError": ProviderErrorCode.ERR_SESSION_FAILED,
        "BridgeEmbedError": ProviderErrorCode.ERR_EMBED_FAILED,
        "BridgeSdkError": ProviderErrorCode.ERR_SDK_ERROR,
        "BridgeTimeoutError": ProviderErrorCode.ERR_TIMEOUT,
        "BridgeCancelledError": ProviderErrorCode.ERR_TIMEOUT,
        "BridgeModelError": ProviderErrorCode.ERR_SDK_ERROR,
    }

    @staticmethod
    def _map_bridge_error(exc: Exception) -> ProviderError:
        """把 Bridge 异常映射为 Provider 级错误（保持 Day3 契约语义）。"""
        cls_name = type(exc).__name__
        code = EmbeddingProvider._BRIDGE_ERROR_MAP.get(
            cls_name, ProviderErrorCode.ERR_UNKNOWN
        )
        return ProviderError(code, str(exc), bridge_error=cls_name)

    def __init__(self, so_path: Optional[str] = None) -> None:
        if _bridge is None:
            raise RuntimeError(_IMPORT_ERROR)

        params = _bridge.BridgeInitParams()
        if so_path is not None:
            params.so_path = so_path

        self._bridge = _bridge.EmbeddingBridge(params)
        self._dimension: Optional[int] = None

    # ── 生命周期 ──

    def start(self) -> None:
        """加载 SDK 并创建会话。重复调用安全（幂等）。"""
        try:
            self._bridge.load()
            self._bridge.create_session()
        except Exception as exc:  # noqa: BLE001 - 统一映射为 Provider 错误
            raise self._map_bridge_error(exc) from exc

    def close(self) -> None:
        """销毁会话并释放 SDK。重复调用安全。"""
        try:
            self._bridge.destroy_session()
        except Exception as exc:  # noqa: BLE001
            raise self._map_bridge_error(exc) from exc

        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._map_bridge_error(exc) from exc

    def __enter__(self) -> "EmbeddingProvider":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── 核心接口（Day3 契约） ──

    def embed(self, text: str, *, timeout_ms: int = 5000) -> EmbeddingResult:
        """
        单条文本向量化。

        输入:
            text: 待向量化文本（空串/空白/超长行为见 Day2 证据）。
            timeout_ms: 单次调用超时（毫秒），默认 5000。当前 Bridge 骨架未实现
                        主动超时中断，该值透传保留（Day4 待实现）。

        返回:
            EmbeddingResult

        异常:
            映射自 BridgeError 的 Python 异常（BridgeError 子类）。
        """
        if not isinstance(text, str):
            raise ProviderError(ProviderErrorCode.ERR_INVALID_TEXT,
                                f"text 必须为 str, 实际 {type(text).__name__}")
        if timeout_ms < 0:
            raise ValueError(f"timeout_ms 不能为负数，实际 {timeout_ms}")

        t0 = time.monotonic()
        try:
            vec = self._bridge.embed(text, timeout_ms)
        except Exception as exc:  # noqa: BLE001 - 统一映射为 Provider 错误
            raise self._map_bridge_error(exc) from exc
        # [TD-A-005-01 主动超时] 超时检测占位：_elapsed_ms 当前未用于强制中断，Day5 启用
        _elapsed_ms = (time.monotonic() - t0) * 1000.0  # noqa: F841

        result = EmbeddingResult(
            vector=list(vec.data),
            dimension=vec.dimension,
            l2_norm=vec.l2_norm,
        )
        if self._dimension is None and result.dimension > 0:
            self._dimension = result.dimension
        return result

    def embed_batch(self, texts: List[str], *, timeout_ms: int = 30000) -> List[EmbeddingResult]:
        """
        批量文本向量化（应用层批处理，顺序调用）。

        输入:
            texts: 文本列表。
            timeout_ms: 整批完成的墙钟时间上限（毫秒），默认 30000。
                        [TD-A-005-02 Batch 并行] 并行策略未定，此值为占位，待实测后调整。
                        当前实现假设顺序调用，单批总超时 = timeout_ms。

        返回:
            与输入顺序一致的 EmbeddingResult 列表。

        异常:
            ValueError: timeout_ms 为负数时抛出。
        """
        if timeout_ms < 0:
            raise ValueError(f"timeout_ms 不能为负数，实际 {timeout_ms}")
        results: List[EmbeddingResult] = []
        deadline = time.monotonic() + timeout_ms / 1000.0
        for text in texts:
            # 仅用剩余时间：每次调用可用 = 剩余墙钟时间（语义清晰，不叠加静态均分）
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            results.append(self.embed(text, timeout_ms=remaining_ms))
        # [TD-A-005-02 Batch 并行] 超时语义待实测：当前仅顺序调用，未强制墙钟中断
        # [NOTE] timeout_ms=0 时 remaining_ms 立即衰减为 1ms（最大努力），未定义"无超时"语义
        return results

    def get_dimension(self) -> int:
        """
        返回当前模型向量维度。

        NOTE: 首次调用若维度未知，会用空串触发一次 embed() 获取维度（有 IPC 副作用）。
        [TD-A-005-03 get_dimension 副作用] 骨架阶段临时方案：Day2 已实测空串返回 768。
        后续应改用 SDK 元信息接口无副作用获取。
        """
        if self._dimension is None:
            r = self.embed("")
            self._dimension = r.dimension
        return self._dimension

    def model_info(self) -> ModelInfo:
        """
        返回当前模型元信息。

        注意:
        - ondevice 为 ASSUMED True（未经 SDK API 验证）。
        - loaded: 本实现中 model_info() 能正常返回即代表模型可用（get_dimension 内部
          已触发 embed 成功，_dimension 必然非空），故 loaded 恒为 True。
          不等同于"SDK 会话已初始化且模型就绪"的精确状态。
        - 精确模型名获取（get_model_list）未在 Day4 骨架实现。
        """
        dim = self.get_dimension()
        return ModelInfo(
            name="ensemble-embd_gte-base_uint8-text",  # [TD-A-005-04 硬编码模型名] Day2 运行日志确认的默认模型，Day5 接入 get_model_list
            dimension=dim,
            ondevice=True,
            loaded=True,  # [TD-A-005-05 loaded 临时语义] get_dimension 已成功即代表模型可用，Day5 精确化
        )
