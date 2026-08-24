"""config.py — D4D 配置加载器（FRZ-CFG-001 / FR-DB-006）

契约来源：deliverables/D4_DB_INITIAL_REQUIREMENTS_20260817.md §FR-DB-006
  - 配置文件 `~/.config/kylin-memory/config.toml`；优先级 CLI > env > file
  - 8 键全量环境变量映射 `KYLIN_MEMORY_*`
  - 文件缺失 → 默认值 + WARN（不 fail-fast）
  - 文件存在但值非法 / 环境变量值非法 → fail-fast

实现要点：
  - Pydantic v2 校验（与项目技术栈一致）
  - `$XDG_RUNTIME_DIR` / `~` 路径展开（systemd 生产由 RuntimeDirectory 提供）
  - 父目录可创建性校验（socket 目录 / db 目录）
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

try:  # Python 3.11+
    import tomllib
except ImportError:  # Python 3.10（项目基线）
    import tomli as tomllib  # type: ignore[no-redef]

logger = logging.getLogger(__name__)

# ── 冻结契约：8 键默认值与环境变量映射（FR-DB-006 表，不得偏离） ──

ENV_PREFIX = "KYLIN_MEMORY_"

# toml 键 -> (Pydantic 字段名, 环境变量名)
KEY_MAP: Dict[str, Tuple[str, str]] = {
    "socket.path": ("socket_path", "KYLIN_MEMORY_SOCKET"),
    "database.path": ("database_path", "KYLIN_MEMORY_DB"),
    "deadline.default_ms": ("deadline_default_ms", "KYLIN_MEMORY_DEADLINE_MS"),
    "retrieve.deadline_ms": ("retrieve_deadline_ms", "KYLIN_MEMORY_RETRIEVE_DEADLINE_MS"),
    "outbox.poll_interval_s": ("outbox_poll_interval_s", "KYLIN_MEMORY_OUTBOX_POLL_INTERVAL_S"),
    "outbox.max_retries": ("outbox_max_retries", "KYLIN_MEMORY_OUTBOX_MAX_RETRIES"),
    "embedding.model": ("embedding_model", "KYLIN_MEMORY_EMBEDDING_MODEL"),
    "log.level": ("log_level", "KYLIN_MEMORY_LOG_LEVEL"),
}

DEFAULTS: Dict[str, object] = {
    "socket_path": "$XDG_RUNTIME_DIR/kylin-memory/memory.sock",
    "database_path": "~/.local/share/kylin-memory/kylin_memory.db",
    "deadline_default_ms": 5000,
    "retrieve_deadline_ms": 150,
    "outbox_poll_interval_s": 1,
    "outbox_max_retries": 3,
    "embedding_model": "default",
    "log_level": "INFO",
}

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class MemoryConfig(BaseModel):
    """校验后的 Memory Service 配置（FRZ-CFG-001 8 键）。"""

    model_config = ConfigDict(extra="forbid")

    socket_path: str = Field(min_length=1)
    database_path: str = Field(min_length=1)
    deadline_default_ms: int = Field(ge=1, le=60000)
    retrieve_deadline_ms: int = Field(ge=1, le=5000)
    outbox_poll_interval_s: int = Field(ge=1, le=60)
    # PR#52 Issue 5：max_retries 必须与冻结 partial index idx_outbox_pending
    # 的 `attempts <= 3` 及 outbox_backlog 的 `attempts <= 3` 保持一致，上限收敛为 3；
    # 若需 >3 重试，须同步重建索引并改 backlog 统计（partial index 无法参数化）。
    outbox_max_retries: int = Field(ge=1, le=3)
    embedding_model: str = Field(min_length=1)
    log_level: str = Field(pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")


def _expand_path(raw: str) -> str:
    """展开 $XDG_RUNTIME_DIR 与 ~ 到绝对路径。"""
    expanded = os.path.expanduser(raw)
    if "$XDG_RUNTIME_DIR" in expanded:
        xdg = os.environ.get("XDG_RUNTIME_DIR")
        if not xdg:  # dev 环境兜底；生产由 systemd RuntimeDirectory 保证
            xdg = "/tmp"
            logger.warning("XDG_RUNTIME_DIR 未设置，socket 默认路径回退到 /tmp（生产由 systemd 提供）")
        expanded = expanded.replace("$XDG_RUNTIME_DIR", xdg)
    return expanded


def _ensure_parent(path: str, what: str) -> None:
    """父目录可创建性校验（FR-DB-006：非空；父目录可创建）。"""
    parent = Path(path).parent
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:  # fail-fast：配置指向不可创建的目录
        raise ValueError(f"{what} 父目录不可创建: {parent} ({exc})") from exc


def _flatten_toml(data: Dict[str, object]) -> Dict[str, object]:
    """把嵌套 toml（如 {socket: {path: ...}}）展开为 {socket.path: ...}。"""
    flat: Dict[str, object] = {}

    def _walk(prefix: str, node: object) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                _walk(f"{prefix}{k}.", v) if prefix else _walk(f"{k}.", v)
        else:
            flat[prefix[:-1]] = node

    _walk("", data)
    return flat


def load_config(
    config_file: Optional[str] = None,
    socket_override: Optional[str] = None,
    db_override: Optional[str] = None,
) -> Tuple[MemoryConfig, List[str]]:
    """加载配置（CLI > env > file > 默认值）。

    Args:
        config_file: 显式配置文件路径；None 时使用 `~/.config/kylin-memory/config.toml`。
        socket_override: CLI --socket 覆盖（优先级最高）。
        db_override: CLI --db 覆盖（优先级最高）。

    Returns:
        (MemoryConfig, warnings)：warnings 为加载过程中的 WARN 信息列表。

    Raises:
        ValueError: 文件存在但值非法 / 环境变量非法 / 目录不可创建（fail-fast）。
    """
    warnings: List[str] = []
    values: Dict[str, object] = dict(DEFAULTS)

    # 1. 文件（缺失 → 默认值 + WARN）
    file_path = Path(config_file) if config_file else Path("~/.config/kylin-memory/config.toml").expanduser()
    if file_path.exists():
        try:
            with file_path.open("rb") as fh:
                raw = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError(f"config.toml 解析失败: {file_path} ({exc})") from exc
        flat = _flatten_toml(raw)
        for toml_key, (field_name, _env) in KEY_MAP.items():
            if toml_key in flat:
                values[field_name] = flat[toml_key]
        # PR#52 Issue 10：未知 toml 键发 WARN（fail-fast 哲学——写错键名如
        # socket.pathh 不应被静默忽略）。extra="forbid" 只看得到已知键，需在此显式提示。
        for unknown_key in sorted(set(flat) - set(KEY_MAP)):
            warnings.append(f"配置文件含未知键 {unknown_key!r}，已忽略（请检查拼写）")
    else:
        warnings.append(f"配置文件不存在 {file_path}，使用全部默认值启动")

    # 2. 环境变量（值非法 → fail-fast，不回退文件值）
    for toml_key, (field_name, env_name) in KEY_MAP.items():
        env_val = os.environ.get(env_name)
        if env_val is not None:
            values[field_name] = env_val

    # 3. CLI 覆盖（最高优先级）
    if socket_override:
        values["socket_path"] = socket_override
    if db_override:
        values["database_path"] = db_override

    # 4. 路径展开
    values["socket_path"] = _expand_path(str(values["socket_path"]))
    values["database_path"] = _expand_path(str(values["database_path"]))

    # 5. 校验（fail-fast）+ 目录可创建性
    try:
        cfg = MemoryConfig(**values)
    except Exception as exc:
        raise ValueError(f"配置非法（fail-fast，拒绝启动）: {exc}") from exc

    _ensure_parent(cfg.socket_path, "socket.path")
    _ensure_parent(cfg.database_path, "database.path")

    return cfg, warnings
