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

import threading
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
    ERR_MODEL_INVALID = 0x0304   # 模型无效（Bridge ERR_MODEL_INVALID）
    ERR_TIMEOUT = 0x0401         # 超过 timeout_ms（Bridge ERR_TIMEOUT）
    ERR_INVALID_TEXT = 0x0500    # text 非 str 类型（应用层校验，不进 Bridge）
    ERR_CONFIG_CONFLICT = 0x0601 # 单例配置冲突（so_path 与已锁定路径不一致）
    ERR_SESSION_DESTROYED = 0x0202  # 会话已销毁（Bridge destroy 后终态，不可重建）
    ERR_FATAL_FAILURE = 0x0203       # 不可恢复终态（Bridge fatal：已 dlclose/destroy，需进程重启）
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
    """单条文本向量化结果（与 Day3 契约一致）。

    error_code / error_message 用途说明（P2）：
    本实现中失败统一抛 ProviderError（不通过返回值表达错误），
    因此 error_code/error_message 在成功路径恒为 0/None，
    保留字段仅为兼容 Day3 契约与潜在的错误降级场景（如 SDK 返回
    非致命 errorCode 时上层可读取诊断信息）。
    """

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


class _ProviderLifecycle(IntEnum):
    """Provider 实例生命周期状态机（P1-1/P1-3/P1-4）。

    UNINITIALIZED → INITIALIZING → READY
                            ↓ (初始化失败)
                        保持 INITIALIZING（下次 start 重试）
    READY → CLOSED（close 后，允许重新 start → INITIALIZING）
    """

    UNINITIALIZED = 0
    INITIALIZING = 1
    READY = 2
    CLOSED = 3


class EmbeddingProvider:
    """
    Embedding 向量化服务（进程级单例）。

    生命周期模型（P0-1，进程级单例 + 实例状态机）：
    - 通过进程级单例 Bridge 共享 SDK 会话：首次 start() 加载动态库并初始化模型，
      后续调用复用已有 session（不销毁重建——SDK 不允许同进程 session 销毁后重建）。
    - 全局路径锁定：so_path 参数仅在进程内第一个实例创建时生效；
      后续创建不同路径的实例将抛出 ERR_CONFIG_CONFLICT（不静默忽略）。
    - 生命周期边界（模型 B）：close() 后实例可重新 start()（重新取得引用）；
      close() 后未重新 start 时调用 embed() 抛 ERR_SESSION_DESTROYED。
    - 初始化状态机：只有 load + create_session + 初始化 embed 全部成功后
      才进入 READY；初始化失败保持 INITIALIZING，下次 start() 重新尝试。
    """

    # Bridge 异常 → Provider 错误码映射（P1-1：隐藏 Bridge 细节）
    _BRIDGE_ERROR_MAP = {
        "BridgeSoNotFoundError": ProviderErrorCode.ERR_SDK_NOT_LOADED,
        "BridgeLoadError": ProviderErrorCode.ERR_SDK_NOT_LOADED,
        "BridgeSymbolError": ProviderErrorCode.ERR_SDK_NOT_LOADED,
        "BridgeSessionError": ProviderErrorCode.ERR_SESSION_FAILED,
        "BridgeSessionDestroyedError": ProviderErrorCode.ERR_SESSION_DESTROYED,  # P1-1: 销毁终态独立映射
        "BridgeFatalError": ProviderErrorCode.ERR_FATAL_FAILURE,  # P1-High/P1-1: fatal 终态后重试——需进程重启（不再是 ERR_SESSION_FAILED）
        "BridgeEmbedError": ProviderErrorCode.ERR_EMBED_FAILED,
        "BridgeSdkError": ProviderErrorCode.ERR_SDK_ERROR,
        "BridgeTimeoutError": ProviderErrorCode.ERR_TIMEOUT,
        "BridgeCancelledError": ProviderErrorCode.ERR_TIMEOUT,
        "BridgeModelError": ProviderErrorCode.ERR_MODEL_INVALID,  # P1-3: 模型错误独立映射
    }

    @staticmethod
    def _map_bridge_error(exc: Exception) -> ProviderError:
        """把 Bridge 异常映射为 Provider 级错误（保持 Day3 契约语义）。"""
        cls_name = type(exc).__name__
        code = EmbeddingProvider._BRIDGE_ERROR_MAP.get(
            cls_name, ProviderErrorCode.ERR_UNKNOWN
        )
        return ProviderError(code, str(exc), bridge_error=cls_name)

    # ── 进程级单例（P0-1 生命周期模型） ──
    # 麒麟实测：SDK 不允许同一进程内 session 销毁后重建（destroy_session →
    # create_session 会阻塞挂起）；也禁止同一进程多个 .so 句柄共存。
    # 因此所有 EmbeddingProvider 共享同一个 Bridge（进程级单例），
    # session 只创建一次、不销毁，进程退出时统一释放。
    _shared_bridge = None
    _shared_dimension: Optional[int] = None
    _shared_so_path: Optional[str] = None  # 首实例锁定路径（P1-2 配置锁定）
    _ref_count = 0
    # [TD-A-005-06 已解决] 类级锁：保护 Singleton 初始化/重置的并发安全。
    # 当前 Memory Service 启动链路单线程（无并发入口），但防御性加锁使
    # 后续引入并发初始化入口时无需升级严重度（台账验收标准）。
    _singleton_lock = threading.Lock()
    _DEFAULT_SO_PATH = "/usr/lib/x86_64-linux-gnu/libkysdk-coreai-embedding.so.1"  # x86_64 宿主证据

    @staticmethod
    def _normalize_so_path(so_path: Optional[str]) -> Optional[str]:
        """so_path 归一化（P2）：None 与显式默认路径视为一致。"""
        if so_path is None:
            return None
        if so_path == EmbeddingProvider._DEFAULT_SO_PATH:
            return None  # 显式默认 == 未指定（None）
        return so_path

    def __init__(self, so_path: Optional[str] = None) -> None:
        if _bridge is None:
            raise RuntimeError(_IMPORT_ERROR)

        norm_so_path = self._normalize_so_path(so_path)

        # [TD-A-005-06] 类级锁：Singleton 创建/配置锁定为临界区（并发安全）
        with EmbeddingProvider._singleton_lock:
            if EmbeddingProvider._shared_bridge is None:
                params = _bridge.BridgeInitParams()
                if norm_so_path is not None:
                    params.so_path = norm_so_path
                EmbeddingProvider._shared_bridge = _bridge.EmbeddingBridge(params)
                EmbeddingProvider._shared_so_path = norm_so_path
                EmbeddingProvider._shared_dimension = None
            else:
                # P1-2: 单例配置锁定——不同路径必须明确报冲突，不静默忽略
                if norm_so_path != EmbeddingProvider._shared_so_path:
                    raise ProviderError(
                        ProviderErrorCode.ERR_CONFIG_CONFLICT,
                        f"so_path 冲突: 已锁定 {EmbeddingProvider._shared_so_path!r}, "
                        f"传入 {so_path!r}（进程级单例仅首实例路径生效）")

        self._bridge = EmbeddingProvider._shared_bridge
        self._dimension: Optional[int] = None
        self._lifecycle = _ProviderLifecycle.UNINITIALIZED

    # ── 生命周期 ──

    def start(self) -> None:
        """启动 Provider：加载 SDK、创建会话（仅首次）、完成模型初始化。
        重复调用安全（幂等）；close 后允许重新 start（模型 B）。

        生命周期模型（P0-1，进程级单例 + 状态机）：
        1. 麒麟实测 SDK 不允许同一进程 session 销毁后重建（会阻塞挂起），
           因此 session 进程内只创建一次，start() 复用已有 session。
        2. create_session 后必须至少完成一次成功 embed（模型加载就绪）
           才能进入 READY；初始化 embed 失败保持 INITIALIZING，下次 start 重试。
        """
        if self._lifecycle == _ProviderLifecycle.READY:
            return  # 已就绪：幂等

        self._lifecycle = _ProviderLifecycle.INITIALIZING
        try:
            self._bridge.load()  # 幂等：已加载则直接返回
            if not self._bridge.has_session:
                self._bridge.create_session()
            # 初始化 embed：模型就绪验证 + 获取维度（每次 start 都重新验证，P1-3）
            init = self._bridge.embed("", 0)
            if init.dimension <= 0:
                raise ProviderError(ProviderErrorCode.ERR_MODEL_INVALID,
                                    f"初始化 embed 返回非法维度: {init.dimension}")
            EmbeddingProvider._shared_dimension = init.dimension
            EmbeddingProvider._ref_count += 1
            self._lifecycle = _ProviderLifecycle.READY
        except Exception as exc:  # noqa: BLE001 - 统一映射为 Provider 错误
            # 初始化失败：保持 INITIALIZING（下次 start 重试），不置 READY（P1-3）
            self._lifecycle = _ProviderLifecycle.INITIALIZING
            # 仅当"load 前失败"（.so 不存在等，Bridge 未加载任何句柄且未进入
            # 不可恢复终态）且无引用时，才允许重置 Singleton，让后续实例用正确
            # 路径重新初始化。
            # 若失败发生在 load 成功后（create_session/初始化 embed 失败），
            # 或已进入 fatal 终态（dlsym 缺失已 dlclose / init_session 失败已
            # destroy，P1-High 方案 A），不得重置单例：SDK 不允许同进程
            # dlclose→dlopen / destroy→create，重置会重新触发危险生命周期。
            # 此时保留共享 Bridge，后续 start()（同实例或新实例）复用同一
            # Bridge，由 fatal_failure_ 终态稳定返回错误。
            if (EmbeddingProvider._ref_count == 0
                    and not self._bridge.loaded
                    and not self._bridge.fatal_failure):
                # [TD-A-005-06] 与 __init__ 同锁：Singleton 重置为临界区
                with EmbeddingProvider._singleton_lock:
                    try:
                        EmbeddingProvider._shared_bridge.destroy_session()
                    except Exception:  # noqa: BLE001 - 恢复路径尽力而为
                        pass
                    EmbeddingProvider._shared_bridge = None
                    EmbeddingProvider._shared_so_path = None
                    EmbeddingProvider._shared_dimension = None
            if isinstance(exc, ProviderError):
                raise
            raise self._map_bridge_error(exc) from exc

    def close(self) -> None:
        """释放本 Provider 对共享 session 的引用。

        语义（模型 B，P1-1/P1-4）：
        - 未启动实例 close() 为 no-op（不减少他人引用）。
        - 已启动实例 close() 减引用并置 CLOSED，允许重新 start()。
        - 重复 close() 为 no-op（_lifecycle 非 READY 时不再减）。
        - 不销毁 session（SDK 不允许同进程 session 销毁重建），
          session 保持存活到进程退出，由共享 Bridge 析构时统一释放。
        """
        if self._lifecycle == _ProviderLifecycle.READY:
            if EmbeddingProvider._ref_count > 0:
                EmbeddingProvider._ref_count -= 1
            self._lifecycle = _ProviderLifecycle.CLOSED
        # 非 READY（UNINITIALIZED/CLOSED/INITIALIZING）→ no-op（P1-1）

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
            timeout_ms: 单次调用超时（毫秒），默认 5000。
                        [TD-A-005-01 主动超时] Day4 未实现主动超时中断，
                        该值当前无实际效果，仅透传保留，Day5 实现。

        返回:
            EmbeddingResult

        异常:
            ProviderError: 失败时抛出；ProviderError.code 为 Provider 级错误码
                （ERR_SDK_NOT_LOADED / ERR_SESSION_FAILED / ERR_EMBED_FAILED /
                ERR_SDK_ERROR / ERR_MODEL_INVALID / ERR_TIMEOUT /
                ERR_SESSION_DESTROYED / ERR_FATAL_FAILURE / ERR_UNKNOWN）；
                ProviderError.bridge_error 仅用于诊断（原始 Bridge 异常类型名）。
            非字符串输入抛 ProviderError(ERR_INVALID_TEXT)。
            timeout_ms 为负数抛 ValueError（参数校验在进入 Bridge 之前）。
        """
        if not isinstance(text, str):
            raise ProviderError(ProviderErrorCode.ERR_INVALID_TEXT,
                                f"text 必须为 str, 实际 {type(text).__name__}")
        if timeout_ms < 0:
            raise ValueError(f"timeout_ms 不能为负数，实际 {timeout_ms}")
        # 生命周期检查（P1-4 模型 B）：READY 前/CLOSED 后未 restart → 明确错误
        if self._lifecycle == _ProviderLifecycle.CLOSED:
            raise ProviderError(ProviderErrorCode.ERR_SESSION_DESTROYED,
                                "实例已 close，请先重新 start()")
        if self._lifecycle != _ProviderLifecycle.READY:
            raise ProviderError(ProviderErrorCode.ERR_SESSION_FAILED,
                                f"实例未就绪（状态 {self._lifecycle.name}），请先 start()")

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
        if EmbeddingProvider._shared_dimension is None and result.dimension > 0:
            EmbeddingProvider._shared_dimension = result.dimension
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
        返回当前模型向量维度（无副作用——TD-A-005-03 已解决）。

        start() 完成初始化 embed 时已把维度写入 _shared_dimension（第 219 行），
        正常路径（start 后）直接返回，**不再触发空串 embed（消除 IPC 副作用）**。

        防御路径：若在未 start() 前调用（非法用法），_shared_dimension 可能为
        None——保留空串 embed fallback（与 Day2 实测空串返回 768 一致），
        保证行为兼容但不作为正常路径。
        """
        if EmbeddingProvider._shared_dimension is None:
            r = self.embed("")  # 仅防御：未 start 前的非法调用
            EmbeddingProvider._shared_dimension = r.dimension
        return EmbeddingProvider._shared_dimension

    def model_info(self) -> ModelInfo:
        """
        返回当前模型元信息。

        注意:
        - ondevice 为 ASSUMED True（未经 SDK API 验证）。
        - loaded（TD-A-005-05 已解决）：基于生命周期状态精确化——仅当
          _lifecycle == READY（会话已初始化且模型就绪）时 loaded=True。
        - 模型名（TD-A-005-04 已解决）：通过 Bridge get_default_model_name()
          查询 SDK 真实模型名；查询失败/符号缺失时回退 Day2 运行日志确认的
          默认模型名（ensemble-embd_gte-base_uint8-text）。
        """
        loaded = self._lifecycle == _ProviderLifecycle.READY
        default_name = "ensemble-embd_gte-base_uint8-text"  # Day2 日志确认的默认模型
        if not loaded:
            return ModelInfo(
                name=default_name,
                dimension=EmbeddingProvider._shared_dimension or 0,
                ondevice=True,
                loaded=False,
            )
        dim = self.get_dimension()
        # [TD-A-005-04] 真实模型名：SDK get_model_list 查询（可选符号，失败回退默认）
        name = default_name
        try:
            real = self._bridge.get_default_model_name()
            if real:
                name = real
        except Exception:  # noqa: BLE001 - 查询失败回退默认名，不影响主链路
            pass
        return ModelInfo(
            name=name,
            dimension=dim,
            ondevice=True,
            loaded=True,
        )
