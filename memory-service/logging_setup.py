"""logging_setup.py — D4D 日志配置（部署冻结 §1.1 / NFR-4）

约定：
  - 日志文件 `~/.local/state/kylin-memory/memory-service.log`（目录 0700）
  - 级别由配置 `log.level` 控制（FRZ-CFG-001 8 键之一）
  - 禁止记录 content 正文 / PII / 密钥；业务层日志点自行遵守
  - stderr 始终输出（便于 systemd journal 捕获）
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR_DEFAULT = "~/.local/state/kylin-memory"
LOG_FILE_NAME = "memory-service.log"


def setup_logging(
    level: str = "INFO",
    log_dir: str | None = None,
    *,
    log_file: bool = True,
) -> logging.Logger:
    """初始化根日志（一次调用，幂等）。

    Args:
        level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）。
        log_dir: 日志目录；None 时用 `~/.local/state/kylin-memory`。
        log_file: 是否写文件（测试可关闭，只留 stderr）。
    """
    root = logging.getLogger()
    if getattr(root, "_kylin_configured", False):
        return logging.getLogger("kylin.memory")

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    if log_file:
        log_path = Path(log_dir or LOG_DIR_DEFAULT).expanduser()
        try:
            log_path.mkdir(parents=True, exist_ok=True, mode=0o700)
            fh = RotatingFileHandler(
                log_path / LOG_FILE_NAME,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError as exc:
            # 日志目录不可写不阻塞启动：stderr 仍可用，记录一条 WARN
            root.warning("日志文件不可用，仅 stderr 输出: %s", exc)

    root._kylin_configured = True  # type: ignore[attr-defined]
    return logging.getLogger("kylin.memory")
