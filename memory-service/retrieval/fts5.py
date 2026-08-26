"""V006/D5-B：最小 SQLite FTS5 查询端口。

只做全文召回，不处理回源/过滤/融合；结果以 RetrievalHit（channel=fts5，
1 起始 rank）返回。生产实现需与 SQLite 真源表对齐；这里提供最小可测版本。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from retrieval.contracts import Channel, RetrievalHit, ScoreSemantics


class Fts5Index:
    """内存版 FTS5 索引（测试/最小实现）。"""

    def __init__(self, db: str = ":memory:") -> None:
        self.conn = sqlite3.connect(db)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(content, memory_id UNINDEXED, version_id UNINDEXED, user_id UNINDEXED)"
        )

    def upsert(self, memory_id: str, version_id: str, content: str, user_id: str) -> None:
        self.conn.execute(
            "DELETE FROM memory_fts WHERE memory_id=? AND version_id=? AND user_id=?", (memory_id, version_id, user_id)
        )
        self.conn.execute(
            "INSERT INTO memory_fts(memory_id, version_id, content, user_id) VALUES (?,?,?,?)",
            (memory_id, version_id, content, user_id),
        )
        self.conn.commit()

    def search(
        self,
        query: str,
        user_id: str,
        top_n: int = 10,
        now: Optional[datetime] = None,
    ) -> list[RetrievalHit]:
        """BM25 排序的全文召回，rank 从 1 开始（1=最相关）。"""
        now = now or datetime.now(timezone.utc)
        rows = self.conn.execute(
            "SELECT memory_id, version_id, bm25(memory_fts) AS score FROM memory_fts WHERE memory_fts MATCH ? AND user_id = ? ORDER BY score LIMIT ?",
            (query, user_id, top_n),
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
                    filter_fingerprint="hmac-sha256:k1:" + "a" * 64,
                )
            )
        return hits
