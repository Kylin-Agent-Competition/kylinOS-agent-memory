"""app.py — D4D Memory Service 组装入口（部署冻结 §1.2 ExecStart）

流程：CLI 参数 → 配置加载（FRZ-CFG-001）→ 日志 → DB 引擎（FR-DB-003）
     → 迁移检查/建表 → Outbox Worker（FR-DB-004）→ IPC Gateway 启动（FRZ-IPC）

PR-2（T1.3）：注入 UnitOfWork 工厂 + worker metrics；turn.finalized 注册 seam
（ADR-010 activation 方案 A+B：production 默认不注册，`--register-turn-finalized`
仅供 test/validation profile 使用）。
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
from typing import Optional

from config import load_config
from db.engine import create_db_engine, has_alembic_version, init_schema
from db.uow import UnitOfWork
from gateway.forget_handlers import register_forget_handlers
from gateway.handlers import (
    register_default_handlers,
    register_event_ingest_handler,
    register_turn_finalized_handler,
)
from gateway.preference_handlers import register_preference_handlers
from gateway.registry import HandlerRegistry
from gateway.server import UDSGatewayServer
from logging_setup import setup_logging
from outbox.router import build_outbox_router
from outbox.worker import OutboxWorker
from service.source_resolver import (
    InMemorySourceResolver,
    load_resolver_from_json,
)

logger = logging.getLogger(__name__)


def build_vector_provider(engine, *, cli_path: Optional[str], dimension: Optional[int]):
    """按显式部署参数组装真实 Vector provider；默认保持 provider 未接线。"""
    if cli_path is None and dimension is None:
        return None
    if not cli_path or dimension is None or dimension <= 0:
        raise ValueError("真实 Vector provider 必须同时配置 --vector-cli 与正的 --vector-dimension")
    from retrieval.real_vector_provider import VectorCliClient
    from retrieval.sqlite_vector_provider import SqliteVectorProvider

    return SqliteVectorProvider(
        engine,
        vector_client=VectorCliClient(cli_path, expected_dimension=dimension),
        digest_keys={"d9d-internal": b"kylin-memory-d9d-internal"},
        dimension=dimension,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Kylin Memory Service (D4D)")
    p.add_argument("--socket", default=None, help="UDS socket 路径（覆盖配置/环境变量）")
    p.add_argument("--config", default=None, help="配置文件路径（默认 ~/.config/kylin-memory/config.toml）")
    p.add_argument("--db", default=None, help="SQLite 路径（等价 KYLIN_MEMORY_DB）")
    p.add_argument("--no-migrate", action="store_true", help="跳过建表（生产由 Alembic 迁移）")
    p.add_argument("--no-outbox", action="store_true", help="不启动 Outbox Worker（测试用）")
    p.add_argument(
        "--vector-cli",
        default=os.environ.get("KYLIN_MEMORY_VECTOR_CLI"),
        help="真实 vector_cli 可执行文件（配置后启用 memory.upserted 索引消费）",
    )
    p.add_argument(
        "--vector-dimension",
        type=int,
        default=os.environ.get("KYLIN_MEMORY_VECTOR_DIMENSION"),
        help="真实 Vector collection 维度；必须与 --vector-cli 一起提供",
    )
    p.add_argument(
        "--register-turn-finalized",
        action="store_true",
        help="（仅 test/validation profile）显式注册 turn.finalized + in-memory resolver；"
        "production 默认不注册（ADR-010 activation 方案 A+B）",
    )
    p.add_argument(
        "--register-preference-handlers",
        action="store_true",
        help="（候选契约 CANDIDATE_SYNC，ADR-016 待立项）显式注册偏好 IPC 方法 "
        "preference.list/create/update/rollback/history；production 默认不注册"
        "（未注册 → UNSUPPORTED_METHOD），与 turn.finalized seam 及 #93 候选路线一致",
    )
    p.add_argument(
        "--register-event-ingest",
        action="store_true",
        help="（仅 test/validation profile）显式注册 event.ingest（ADR-014 activation 方案 A+B）；"
        "production 默认不注册（未注册 → UNSUPPORTED_METHOD）",
    )
    p.add_argument(
        "--register-forget-handlers",
        action="store_true",
        help="（仅 test/validation profile）显式注册 forget.preview / forget.execute"
        "（ADR-019 activation 方案 A+B，CANDIDATE/BLOCKED_BY_HOST_MAPPING）；"
        "production 默认不注册（未注册 → UNSUPPORTED_METHOD）",
    )
    p.add_argument(
        "--validation-sources",
        default=None,
        help="（仅 --register-turn-finalized）resolver 映射 JSON 文件路径（M6）；"
        "不提供时为空映射，仅负路径（INTERNAL_ERROR）可验证",
    )
    p.add_argument(
        "--json-logs",
        action="store_true",
        help="JSON 结构化日志（T3.2；production 建议开启，测试默认文本）",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    cfg, warnings = load_config(
        config_file=args.config, socket_override=args.socket, db_override=args.db
    )
    for w in warnings:
        logger.warning("%s", w)

    setup_logging(level=cfg.log_level, json_logs=args.json_logs)

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

    # T1.3：UnitOfWork 工厂（handler 幂等写 + Outbox 同事务）
    def _uow_factory() -> UnitOfWork:
        return UnitOfWork(engine)

    # ADR-010 activation 方案 A+B：production 默认不注册 turn.finalized；
    # 仅 test/validation profile（--register-turn-finalized）显式注册 + 内存 resolver。
    if args.register_turn_finalized:
        # M6.2：--validation-sources 仅在本分支内解析（受控）——
        # 提供 path → 加载 JSON 映射（正向写可验证）；
        # 无 path → 保持空 resolver，仅负路径可验证（logger.warning 注明）。
        resolver = InMemorySourceResolver()
        if args.validation_sources:
            resolver = load_resolver_from_json(args.validation_sources)
            logger.info(
                "validation profile：已加载 validation sources 映射（%s）",
                args.validation_sources,
            )
        else:
            logger.warning(
                "validation profile：未提供 --validation-sources，resolver 为空映射，"
                "仅负路径（resolver 未命中 → INTERNAL_ERROR）可验证"
            )
        register_turn_finalized_handler(registry, uow_factory=_uow_factory, resolver=resolver)
        logger.warning(
            "turn.finalized 已注册（test/validation profile，in-memory resolver）。"
            "production 禁止使用此参数（BLOCKED_BY_HOST_MAPPING）"
        )

    # D7C：偏好 IPC 方法（候选契约 CANDIDATE_SYNC，ADR-016 待立项；随 D7C PR #87 落地）。
    # 契约未冻结前 production 默认不注册（未注册 → UNSUPPORTED_METHOD），
    # 仅 --register-preference-handlers 显式激活（test/validation/demo profile），
    # 对齐 turn.finalized seam 模式与 #93 候选路线（HIGH-1 返工）。
    if args.register_preference_handlers:
        register_preference_handlers(registry, uow_factory=_uow_factory)
        logger.warning(
            "preference.* 已注册（候选契约显式激活 profile）。production 默认不注册（ADR-016 待立项）"
        )

    # ADR-014 activation 方案 A+B：production 默认不注册 event.ingest；
    # 仅 test/validation profile（--register-event-ingest）显式注册。
    # trusted_identity=None = 仅声明内部自洽，非宿主认证证据（L2 HOST_VERIFIED 前保持如此）。
    if args.register_event_ingest:
        register_event_ingest_handler(registry, uow_factory=_uow_factory)
        logger.warning(
            "event.ingest 已注册（test/validation profile，trusted_identity=None）。"
            "production 禁止使用此参数（BLOCKED_BY_HOST_MAPPING）"
        )

    # ADR-019 activation 方案 A+B：production 默认不注册 forget.preview / forget.execute；
    # 仅 test/validation profile（--register-forget-handlers）显式注册。
    # trusted_identity=None = 仅声明内部自洽，非宿主认证证据（L2 HOST_VERIFIED 前保持如此）。
    if args.register_forget_handlers:
        register_forget_handlers(registry, uow_factory=_uow_factory)
        logger.warning(
            "forget.preview / forget.execute 已注册（test/validation profile，"
            "trusted_identity=None）。production 禁止使用此参数（BLOCKED_BY_HOST_MAPPING）"
        )

    worker: Optional[OutboxWorker] = None
    if not args.no_outbox:
        # D9D D-REQ-05：注入 OutboxRouter（统一消费路由）。
        vector_provider = build_vector_provider(
            engine, cli_path=args.vector_cli, dimension=args.vector_dimension
        )
        router = build_outbox_router(
            vector_provider=vector_provider,
            embedding_service=None,
        )
        worker = OutboxWorker(
            engine,
            poll_interval_s=cfg.outbox_poll_interval_s,
            max_retries=cfg.outbox_max_retries,
            consumer=router.route,
        )
        worker.start()

    server = UDSGatewayServer(
        cfg.socket_path,
        registry,
        engine=engine,
        default_deadline_ms=cfg.deadline_default_ms,
        # T3.1：health 携带 outbox backlog（worker.metrics() 现成；worker=None 时无）
        worker_metrics=worker.metrics if worker is not None else None,
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
