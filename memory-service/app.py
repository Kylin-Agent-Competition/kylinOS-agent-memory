"""app.py — D4D Memory Service 组装入口（部署冻结 §1.2 ExecStart）

流程：CLI 参数 → 配置加载（FRZ-CFG-001）→ 日志 → DB 引擎（FR-DB-003）
     → 迁移检查/建表 → Outbox Worker（FR-DB-004）→ IPC Gateway 启动（FRZ-IPC）
"""

from __future__ import annotations

import argparse
import logging
import threading
from typing import Optional

from config import load_config
from db.engine import create_db_engine, has_alembic_version, init_schema
from gateway.handlers import register_default_handlers
from gateway.registry import HandlerRegistry
from gateway.server import UDSGatewayServer
from logging_setup import setup_logging
from outbox.worker import OutboxWorker

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kylin Memory Service (D4D)")
    p.add_argument("--socket", default=None, help="UDS socket 路径（覆盖配置/环境变量）")
    p.add_argument("--config", default=None, help="配置文件路径（默认 ~/.config/kylin-memory/config.toml）")
    p.add_argument("--db", default=None, help="SQLite 路径（等价 KYLIN_MEMORY_DB）")
    p.add_argument("--no-migrate", action="store_true", help="跳过建表（生产由 Alembic 迁移）")
    p.add_argument("--no-outbox", action="store_true", help="不启动 Outbox Worker（测试用）")
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    cfg, warnings = load_config(
        config_file=args.config, socket_override=args.socket, db_override=args.db
    )
    for w in warnings:
        logger.warning("%s", w)

    setup_logging(level=cfg.log_level)

    engine = create_db_engine(cfg.database_path)
    if args.no_migrate:
        # 生产模式：唯一数据库初始化/升级入口为 Alembic（FR-DB-002）。
        # 启动校验 alembic_version 表存在——不存在则说明 operator 未先跑
        # `alembic upgrade head`，此时以 create_all 兜底会重新引入双 schema
        # truth source 分叉，故 fail-fast 拒绝启动（PR#52 Issue 6）。
        if not has_alembic_version(engine):
            logger.error(
                "生产模式（--no-migrate）要求先执行 `alembic upgrade head`："
                "未检测到 alembic_version 表，拒绝启动（PR#52 Issue 6）。"
            )
            return 2
        logger.info("生产模式：alembic_version 校验通过，schema 由 Alembic 管理")
    else:
        # 开发/验证快速建库；生产迁移走 `alembic upgrade head`（FR-DB-002）
        init_schema(engine)
        logger.info("schema 就绪: %s", cfg.database_path)
        logger.warning(
            "开发模式建库（init_schema=create_all，绕过 Alembic）。"
            "生产环境必须先 `alembic upgrade head`，再以 `--no-migrate` 启动，"
            "避免两套建表路径 default 语义分叉（PR#52 Issue 6）。"
        )

    registry = HandlerRegistry()
    register_default_handlers(registry)

    worker: Optional[OutboxWorker] = None
    if not args.no_outbox:
        worker = OutboxWorker(
            engine,
            poll_interval_s=cfg.outbox_poll_interval_s,
            max_retries=cfg.outbox_max_retries,
        )
        worker.start()

    server = UDSGatewayServer(
        cfg.socket_path,
        registry,
        engine=engine,
        default_deadline_ms=cfg.deadline_default_ms,
    )

    def _run_server() -> None:
        server.start()

    server_thread = threading.Thread(target=_run_server, name="ipc-gateway", daemon=True)
    server_thread.start()
    logger.info("Memory Service 就绪（socket=%s）", cfg.socket_path)

    try:
        while server_thread.is_alive():
            server_thread.join(timeout=1.0)
    except KeyboardInterrupt:
        logger.info("收到中断，正在停止…")
    finally:
        server.stop()
        if worker is not None:
            worker.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
