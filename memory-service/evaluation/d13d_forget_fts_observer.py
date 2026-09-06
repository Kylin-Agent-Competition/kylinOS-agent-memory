"""d13d_forget_fts_observer.py — Forget realtime/rebuild 检索观测（FTS5 真实通道）。

E 授权裁定（2026-09-07）：本 VM 以 production ``Fts5Index`` 为唯一 approved
真实检索通道（d13d-validation-profile-v2）。语义对齐 E 规则 2/4：
- pre-delete probe 必须先命中确认目标（否则删除后 miss 无证明力 → fail-closed）；
- realtime = execute + FTS 删除消费（从索引移除已执行目标）后的真实检索；
- rebuild  = 从当前真源重建新索引代次后的真实检索（独立代码路径，不复制 realtime）；
- residual = 确认目标 logical ID 是否真实出现在检索返回（knowledge:/preference: tag）。

不读 Gold/expected；不做语义相似判定；不手工 SELECT 冒充检索返回。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.engine import Connection, Engine

from db.schema import memory_entries, memory_items, memory_versions
from retrieval.contracts import ObjectType, Watermark, WatermarkDomain, WatermarkKind
from retrieval.evaluation import ForgetResidualSample, ForgetResidualPhase
from retrieval.fts5 import Fts5Index
from service.d13d_forget_observability import ForgetRetrievalObservation


@dataclass(frozen=True)
class _IndexedDoc:
    tagged_id: str
    version_id: str
    text: str


def _content_text(content: object) -> str:
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return content
        content = parsed
    if isinstance(content, dict):
        value = content.get("value")
        if isinstance(value, str) and value.strip():
            return value
        return json.dumps(content, ensure_ascii=False)
    if isinstance(content, str):
        return content
    return ""


def _active_docs(conn: Connection, *, user_id: str) -> List[_IndexedDoc]:
    """从真实真源读取 active 索引文档（knowledge + preference 当前版本）。"""
    docs: List[_IndexedDoc] = []
    krows = conn.execute(
        select(
            memory_entries.c.id,
            memory_entries.c.version,
            memory_entries.c.content,
        )
        .where(
            and_(
                memory_entries.c.user_id == user_id,
                memory_entries.c.is_deleted == 0,
            )
        )
        .order_by(memory_entries.c.id.asc())
    ).mappings().all()
    for row in krows:
        text = _content_text(row["content"])
        if not text.strip():
            continue
        docs.append(
            _IndexedDoc(
                tagged_id=f"knowledge:{int(row['id'])}",
                version_id=f"v{int(row['version'])}",
                text=text,
            )
        )
    prows = conn.execute(
        select(
            memory_items.c.id.label("item_id"),
            memory_items.c.preference_key,
            memory_versions.c.version,
            memory_versions.c.preference_value,
        )
        .join(memory_versions, memory_versions.c.id == memory_items.c.current_version_id)
        .where(
            and_(
                memory_items.c.user_id == user_id,
                memory_versions.c.is_current == 1,
                memory_versions.c.memory_status != "removed",
            )
        )
        .order_by(memory_items.c.id.asc())
    ).mappings().all()
    for row in prows:
        key = str(row["preference_key"])
        value = str(row["preference_value"])
        if not (key.strip() or value.strip()):
            continue
        docs.append(
            _IndexedDoc(
                tagged_id=f"preference:{int(row['item_id'])}",
                version_id=f"v{int(row['version'])}",
                text=f"{key} {value}".strip(),
            )
        )
    return docs


class D13DForgetFtsObserver:
    """FTS5 realtime/rebuild Forget 检索观测器（绑定一个 isolated runtime binding）。"""

    def __init__(self, engine: Engine, *, user_id: str, fts_db: str) -> None:
        if not isinstance(engine, Engine):
            raise TypeError("engine must be a SQLAlchemy Engine")
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValueError("user_id must be a non-blank string")
        if not isinstance(fts_db, str) or not fts_db.strip():
            raise ValueError("fts_db path must be non-blank")
        self._engine = engine
        self._user_id = user_id
        self._fts_db = fts_db
        self._docs: Dict[str, _IndexedDoc] = {}
        self._fts: Optional[Fts5Index] = None
        self._initialized = False
        self._realtime_generation = 0
        self._rebuild_generation = 0

    # ── 构建/同步 ──

    def initialize(self) -> None:
        """pre-delete：从当前真源建 FTS 索引并记录 docs（供 probe/查询文本）。"""
        if self._initialized:
            return
        with self._engine.connect() as conn:
            docs = _active_docs(conn, user_id=self._user_id)
        fts = Fts5Index(db=self._fts_db)
        for doc in docs:
            fts.upsert(
                memory_id=doc.tagged_id,
                version_id=doc.version_id,
                content_summary=doc.text,
                user_id=self._user_id,
                object_type=(
                    ObjectType.KNOWLEDGE
                    if doc.tagged_id.startswith("knowledge:")
                    else ObjectType.PREFERENCE
                ),
            )
            self._docs[doc.tagged_id] = doc
        self._fts = fts
        self._initialized = True

    def _rebuild_fts(self) -> Fts5Index:
        """rebuild：从当前真源（execute 后已删除目标）重建新索引代次。"""
        with self._engine.connect() as conn:
            docs = _active_docs(conn, user_id=self._user_id)
        generation_db = f"{self._fts_db}.rebuild"
        fts = Fts5Index(db=generation_db)
        for doc in docs:
            fts.upsert(
                memory_id=doc.tagged_id,
                version_id=doc.version_id,
                content_summary=doc.text,
                user_id=self._user_id,
                object_type=(
                    ObjectType.KNOWLEDGE
                    if doc.tagged_id.startswith("knowledge:")
                    else ObjectType.PREFERENCE
                ),
            )
        return fts

    # ── probe / realtime / rebuild ──

    def probe_pre_delete(self, confirmed: tuple[str, ...]) -> None:
        """pre-delete probe：确认目标必须先能检索到，否则 fail-closed。"""
        if not self._initialized:
            raise ValueError("observer 必须先 initialize()")
        assert self._fts is not None
        for tagged_id in confirmed:
            doc = self._docs.get(tagged_id)
            if doc is None:
                raise ValueError(f"pre-delete probe: no indexed doc for {tagged_id}")
            found = self._fts.search(self._phrase(doc.text), user_id=self._user_id, top_n=20)
            if not any(hit.memory_id == tagged_id for hit in found):
                raise ValueError(f"pre-delete probe miss: {tagged_id}")

    def apply_deletion_payload(self, payload: Dict[str, Any]) -> None:
        """真实 deletion-consumer（FTS 通道）：只消费真实 forget.executed payload。

        解析 payload 的 resolved_target_ids（与 deletion_consumer 同口径）删除索引文档，
        删除成功即该事件 ACK；绝不用 preview 的 confirmed 列表自行删索引。
        """
        if payload.get("user_id") != self._user_id:
            raise ValueError("forget.executed user_id 与 observer user 不一致")
        resolved = payload.get("resolved_target_ids") or []
        version_ids = payload.get("version_ids")
        if version_ids is not None and len(version_ids) != len(resolved):
            raise ValueError("forget.executed version_ids 与 resolved_target_ids 长度不一致")
        if not self._initialized or self._fts is None:
            raise ValueError("observer 必须先 initialize()")
        normalized: List[str] = []
        for raw in resolved:
            token = str(raw)
            if ":" in token:
                kind, _, num = token.partition(":")
                if kind not in ("knowledge", "preference") or not num.isdecimal():
                    raise ValueError(f"forget.executed 目标含未知 kind/非数字 id: {token!r}")
                normalized.append(f"{kind}:{num}")
            else:
                normalized.append(f"knowledge:{token}")
        for tagged_id in normalized:
            doc = self._docs.get(tagged_id)
            if doc is not None:
                self._fts.delete(doc.tagged_id, doc.version_id, self._user_id)
        self._realtime_generation += 1

    def realtime(self, confirmed: tuple[str, ...]) -> ForgetRetrievalObservation:
        """真实 deletion-consumer ACK 之后的真实检索（observer 不自行删索引）。"""
        if not self._initialized:
            raise ValueError("observer 必须先 initialize()")
        assert self._fts is not None
        ranked = self._rank(self._fts, confirmed)
        return self._observation(
            ForgetResidualPhase.REALTIME_DELETE,
            confirmed,
            ranked,
            f"fts:{self._user_id}:realtime:g{self._realtime_generation}",
        )

    def rebuild(self, confirmed: tuple[str, ...]) -> ForgetRetrievalObservation:
        """full rebuild 后真实检索（新索引代次，代次由实际 rebuild 产生）。"""
        self._rebuild_generation += 1
        fts = self._rebuild_fts()
        ranked = self._rank(fts, confirmed)
        return self._observation(
            ForgetResidualPhase.REBUILD,
            confirmed,
            ranked,
            f"fts:{self._user_id}:rebuild:g{self._rebuild_generation}",
        )

    # ── 内部 ──

    def _rank(self, fts: Fts5Index, confirmed: tuple[str, ...]) -> tuple[str, ...]:
        hits: set[str] = set()
        for tagged_id in confirmed:
            doc = self._docs.get(tagged_id)
            if doc is None:
                continue
            found = fts.search(self._phrase(doc.text), user_id=self._user_id, top_n=20)
            hits.update(hit.memory_id for hit in found)
        return tuple(sorted(hits))

    @staticmethod
    def _phrase(text: str) -> str:
        """FTS5 短语查询，避免连字符/空格被当成查询操作符。"""
        return '"' + text.replace('"', '""') + '"'
    def _observation(
        self,
        phase: ForgetResidualPhase,
        confirmed: tuple[str, ...],
        ranked: tuple[str, ...],
        snapshot_id: str,
    ) -> ForgetRetrievalObservation:
        sample = ForgetResidualSample(
            query_id=f"{phase.value}-{self._user_id}",
            confirmed_target_ids=confirmed,
            ranked_ids=ranked,
        )
        generation = (
            self._realtime_generation if phase == ForgetResidualPhase.REALTIME_DELETE
            else self._rebuild_generation
        )
        return ForgetRetrievalObservation(
            sample=sample,
            dataset_version="d13d-forget-v2",
            source_snapshot_id=snapshot_id,
            source_watermark=Watermark(
                domain=WatermarkDomain(
                    scope_id=f"user:{self._user_id}",
                    stream="forget_fts5",
                    partition="default",
                    source_generation=snapshot_id,
                ),
                kind=WatermarkKind.MONOTONIC_INT,
                value=generation,
            ),
        )


def build_fts_observer(
    binding: Any, artifact: Any, sample_id: str
) -> D13DForgetFtsObserver:
    """OBSERVATION_PROFILES['d13d-validation-profile-v2'] 的受控 builder。

    fts db 放在该 sample 的 isolated runtime 目录内，与 runtime.db 同代次隔离。
    """
    entry = next(
        (s for s in artifact.get("samples", []) if s.get("sample_id") == sample_id), None
    )
    if entry is None:
        raise ValueError(f"artifact has no entry for {sample_id}")
    fts_db = str(binding.db_path.with_name("fts.db"))
    observer = D13DForgetFtsObserver(
        binding.engine, user_id=str(entry["user_id"]), fts_db=fts_db
    )
    observer.initialize()
    return observer