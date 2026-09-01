"""D10-B：从 SQLite 真源读取确定性的 Vector 重建快照。

本模块只在调用方已开启的 SQLite 读事务中读取 ``memory_entries``。它不创建
Vector Collection、不调用 Embedding、不激活代次，也不推断遗忘授权或水位语义。
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.engine import Connection

from db.schema import memory_entries
from retrieval.contracts import Watermark

IndexTextResolver = Callable[[Mapping[str, object]], str | None]


@dataclass(frozen=True)
class SqliteVectorSnapshotRecord:
    """可供后续向量化的 SQLite 真源记录，不含向量或代次决策。"""

    memory_entry_id: int
    source_version: int
    user_id: str
    entry_type: str
    index_text: str


@dataclass(frozen=True)
class SqliteVectorSnapshotRejection:
    """单条记录未进入重建快照的安全原因。"""

    memory_entry_id: int
    reason: str


@dataclass(frozen=True)
class SqliteVectorSnapshot:
    """同一 SQLite 读事务中取得的、用户限定的重建输入快照。"""

    source_snapshot_id: str
    source_watermark: Watermark
    records: list[SqliteVectorSnapshotRecord]
    rejections: list[SqliteVectorSnapshotRejection]


class SqliteVectorSnapshotReader:
    """读取已提交且未软删除的 ``memory_entries``，并维持用户边界。"""

    def __init__(self, index_text_resolver: IndexTextResolver) -> None:
        if not callable(index_text_resolver):
            raise TypeError("索引文本解析器必须可调用")
        self._index_text_resolver = index_text_resolver

    def read(
        self,
        conn: Connection,
        *,
        user_id: str,
        source_snapshot_id: str,
        source_watermark: Watermark,
    ) -> SqliteVectorSnapshot:
        """在调用方已开启的 SQLite 事务内读取确定性用户快照。"""
        if not conn.in_transaction():
            raise ValueError("SQLite 事务必须由调用方先开启")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("用户必须非空")
        if not isinstance(source_snapshot_id, str) or not source_snapshot_id.strip():
            raise ValueError("快照标识必须非空")
        if not isinstance(source_watermark, Watermark):
            raise TypeError("快照水位必须是 Watermark")

        rows = conn.execute(
            select(
                memory_entries.c.id,
                memory_entries.c.user_id,
                memory_entries.c.entry_type,
                memory_entries.c.content,
                memory_entries.c.version,
            )
            .where(
                memory_entries.c.user_id == user_id,
                memory_entries.c.is_deleted == 0,
            )
            .order_by(memory_entries.c.id.asc())
        ).mappings()

        records: list[SqliteVectorSnapshotRecord] = []
        rejections: list[SqliteVectorSnapshotRejection] = []
        for row in rows:
            memory_entry_id = int(row["id"])
            source_version = int(row["version"])
            if source_version <= 0:
                rejections.append(
                    SqliteVectorSnapshotRejection(memory_entry_id, "source_version_invalid")
                )
                continue
            payload = self._parse_content(row["content"])
            if payload is None:
                rejections.append(
                    SqliteVectorSnapshotRejection(memory_entry_id, "content_json_invalid")
                )
                continue
            if not isinstance(payload, dict):
                rejections.append(
                    SqliteVectorSnapshotRejection(memory_entry_id, "content_json_not_object")
                )
                continue
            try:
                index_text = self._index_text_resolver(payload)
            except Exception:  # 解析策略由调用方提供，单条失败不得扩大快照范围。
                index_text = None
            if not isinstance(index_text, str) or not index_text.strip():
                rejections.append(
                    SqliteVectorSnapshotRejection(memory_entry_id, "index_text_unavailable")
                )
                continue
            records.append(
                SqliteVectorSnapshotRecord(
                    memory_entry_id=memory_entry_id,
                    source_version=source_version,
                    user_id=str(row["user_id"]),
                    entry_type=str(row["entry_type"]),
                    index_text=index_text.strip(),
                )
            )

        return SqliteVectorSnapshot(
            source_snapshot_id=source_snapshot_id,
            source_watermark=source_watermark,
            records=records,
            rejections=rejections,
        )

    @staticmethod
    def _parse_content(value: object) -> object | None:
        if not isinstance(value, str):
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
