"""V006/D5-B：最小 SQLite FTS5 查询端口。

只做全文召回，不处理回源/过滤/融合；结果以 RetrievalHit（channel=fts5，
1 起始 rank）返回。`content_summary` 必须来自上游敏感过滤；本端口不会读取或回退到
SQLite 真源正文。生产实现需与 SQLite 真源表对齐；这里提供最小可测版本。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from retrieval.contracts import (
    Channel,
    KnowledgeIndexMetadata,
    ObjectType,
    RetrievalFilter,
    RetrievalHit,
    ScoreSemantics,
    filter_fingerprint_digest,
)


class Fts5Index:
    """内存版 FTS5 索引（测试/最小实现）。"""

    def __init__(self, db: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5("
            "content, memory_id UNINDEXED, version_id UNINDEXED, user_id UNINDEXED, "
            "object_type UNINDEXED, knowledge_type UNINDEXED, "
            "primary_category UNINDEXED, source_event_id UNINDEXED, "
            "memory_status UNINDEXED)"
        )

    def upsert(
        self,
        memory_id: str,
        version_id: str,
        content_summary: str,
        user_id: str,
        *,
        object_type: ObjectType = ObjectType.KNOWLEDGE,
        knowledge: Optional[KnowledgeIndexMetadata] = None,
    ) -> None:
        if knowledge is not None and object_type is not ObjectType.KNOWLEDGE:
            raise ValueError("Knowledge 索引元数据只能用于 knowledge 对象")
        self.conn.execute(
            "DELETE FROM memory_fts WHERE memory_id=? AND version_id=? AND user_id=?", (memory_id, version_id, user_id)
        )
        self.conn.execute(
            "INSERT INTO memory_fts("
            "memory_id, version_id, content, user_id, object_type, knowledge_type, "
            "primary_category, source_event_id, memory_status"
            ") VALUES (?,?,?,?,?,?,?,?,?)",
            (
                memory_id,
                version_id,
                content_summary,
                user_id,
                object_type.value,
                knowledge.knowledge_type if knowledge is not None else None,
                knowledge.primary_category if knowledge is not None else None,
                knowledge.source_event_id if knowledge is not None else None,
                knowledge.memory_status if knowledge is not None else None,
            ),
        )
        self.conn.commit()

    def search(
        self,
        query: str,
        user_id: str,
        top_n: int = 10,
        now: Optional[datetime] = None,
        *,
        filter: Optional[RetrievalFilter] = None,
    ) -> list[RetrievalHit]:
        """BM25 排序的全文召回，rank 从 1 开始（1=最相关）。"""
        now = now or datetime.now(timezone.utc)
        if filter is not None and filter.user_id != user_id:
            raise ValueError("RetrievalFilter.user_id 必须与 FTS5 搜索 user_id 一致")


        if filter is not None:
            fingerprint = filter_fingerprint_digest(filter)
        else:
            fingerprint = filter_fingerprint_digest({"user_id": user_id})
        clauses = ["memory_fts MATCH ?", "user_id = ?"]
        params: list[object] = [query, user_id]

        def add_in(field: str, values: list[str]) -> None:
            if not values:
                return
            placeholders = ",".join("?" for _ in values)
            clauses.append(f"{field} IN ({placeholders})")
            params.extend(values)

        def add_knowledge_in(field: str, values: list[str]) -> None:
            if not values:
                return
            placeholders = ",".join("?" for _ in values)
            clauses.append(
                f"(object_type != ? OR {field} IN ({placeholders}))"
            )
            params.append(ObjectType.KNOWLEDGE.value)
            params.extend(values)

        if filter is not None:
            add_in("object_type", [value.value for value in filter.object_types])
            add_in("memory_status", filter.allowed_memory_statuses)
            add_knowledge_in("knowledge_type", filter.knowledge.knowledge_types)
            add_knowledge_in(
                "primary_category", filter.knowledge.primary_categories
            )
            add_knowledge_in("source_event_id", filter.knowledge.source_event_ids)
            add_knowledge_in("version_id", filter.knowledge.version_ids)

        params.append(top_n)
        rows = self.conn.execute(
            "SELECT memory_id, version_id, bm25(memory_fts) AS score "
            "FROM memory_fts WHERE "
            + " AND ".join(clauses)
            + " ORDER BY score LIMIT ?",
            params,
        ).fetchall()
        hits: list[RetrievalHit] = []
        for rank, row in enumerate(rows, 1):
            hits.append(
                RetrievalHit(
                    memory_id=row["memory_id"],
                    version_id=row["version_id"],
                    user_id=user_id,
                    channel=Channel.FTS5,
                    rank=rank,
                    raw_score=float(row["score"]),
                    score_semantics=ScoreSemantics.BM25,
                    provider="fts5",
                    retrieved_at=now,
                    filter_fingerprint=fingerprint,
                )
            )
        return hits
