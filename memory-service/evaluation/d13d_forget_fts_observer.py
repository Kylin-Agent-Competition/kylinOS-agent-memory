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
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.engine import Connection, Engine

from db.schema import memory_entries, memory_items, memory_versions
from embedding.embedding_service import EmbeddingService
from outbox.deletion_consumer import build_forget_consumer
from providers import ProviderError, ProviderErrorCode
from retrieval.contracts import (
    Outcome,
    ObjectType,
    ProviderResult,
    RetrievalError,
    RetrievalErrorCode,
    VectorDeleteRequest,
    VectorDeleteResult,
    Watermark,
    WatermarkDomain,
    WatermarkKind,
)
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
        self._deleted_keys: set[tuple[str, str]] = set()

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


class D13DForgetFtsDeletionProvider:
    """Validation profile 的 FTS5 deletion port（只开放 delete）。

    它消费正式 ``build_forget_consumer`` 构造并签名的
    :class:`VectorDeleteRequest`，把 selector 精确映射回 observer 当前 FTS 索引。
    目标缺失/映射歧义/deadline 过期均返回真实失败；不提供 upsert/search/rebuild
    等未在本 profile 授权的能力。
    """

    provider = "d13d-fts5-deletion"

    def __init__(self, observer: D13DForgetFtsObserver, *, digest_key_id: str, digest_key: bytes) -> None:
        self._observer = observer
        self._digest_key_id = digest_key_id
        self._digest_key = digest_key
        self._deleted_keys: set[tuple[str, str]] = set()

    def _result(
        self,
        request: VectorDeleteRequest,
        *,
        ok: bool,
        value: Optional[VectorDeleteResult] = None,
        message: Optional[str] = None,
    ) -> ProviderResult[VectorDeleteResult]:
        completed_at = datetime.now(timezone.utc)
        if ok:
            return ProviderResult(
                ok=True,
                value=value,
                provider=self.provider,
                request_id=request.request_id,
                elapsed_ms=0,
                completed_at=completed_at,
            )
        assert message is not None
        return ProviderResult(
            ok=False,
            error=RetrievalError(
                code=RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR,
                message=message,
                retryable=False,
                stage="delete",
                provider=self.provider,
            ),
            provider=self.provider,
            request_id=request.request_id,
            elapsed_ms=0,
            completed_at=completed_at,
        )

    def delete(self, request: VectorDeleteRequest) -> ProviderResult[VectorDeleteResult]:
        observer = self._observer
        if request.user_id != observer._user_id or not observer._initialized or observer._fts is None:
            return self._result(request, ok=False, message="FTS deletion provider is not bound to the observer")

        canonical = request.model_dump(
            mode="json",
            exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
        )
        from retrieval.contracts import digest_from_canonical

        if digest_from_canonical(
            self._digest_key_id, self._digest_key, canonical
        ) != request.payload_hash:
            return self._result(request, ok=False, message="FTS deletion payload hash mismatch")
        if datetime.now(timezone.utc) > request.deadline_at:
            return self._result(request, ok=False, message="FTS deletion deadline exceeded")

        memory_ids = request.selector.memory_ids
        version_ids = request.selector.version_ids or []
        if len(version_ids) != len(memory_ids):
            return self._result(request, ok=False, message="FTS deletion version_ids are not aligned")

        matched = 0
        deleted = 0
        try:
            for memory_id, version_id in zip(memory_ids, version_ids):
                candidates = [
                    (tagged_id, doc)
                    for tagged_id, doc in observer._docs.items()
                    if tagged_id.rpartition(":")[2] == str(memory_id)
                    and doc.version_id == str(version_id)
                ]
                deletion_key = (str(memory_id), str(version_id))
                if not candidates and deletion_key in self._deleted_keys:
                    continue
                if len(candidates) != 1:
                    return self._result(
                        request,
                        ok=False,
                        message=(
                            f"FTS deletion target is missing or ambiguous: {memory_id}:{version_id}"
                        ),
                    )
                tagged_id, doc = candidates[0]
                observer._fts.delete(doc.tagged_id, doc.version_id, request.user_id)
                self._deleted_keys.add(deletion_key)
                observer._realtime_generation += 1
                matched += 1
                deleted += 1
        except Exception as exc:
            return self._result(request, ok=False, message=f"FTS deletion failed: {type(exc).__name__}")

        outcome = Outcome.APPLIED if deleted else Outcome.NO_OP
        return self._result(
            request,
            ok=True,
            value=VectorDeleteResult(
                matched_count=matched,
                deleted_count=deleted,
                index_generation=request.index_generation,
                applied_watermark=request.source_watermark,
                outcome=outcome,
            ),
        )


class _ValidationNoEmbeddingProvider:
    """No-embed lifecycle provider for the validation deletion consumer.

    forget deletion does not call embed; any accidental call fails closed.
    """

    def start(self) -> None:
        return None

    def close(self) -> None:
        return None

    def get_dimension(self) -> int:
        return 0

    def embed(self, text: str, *, timeout_ms: int = 5000):
        raise ProviderError(
            ProviderErrorCode.ERR_SDK_NOT_LOADED,
            "D13D FTS deletion consumer must not call embedding",
        )


class _ValidationNoExtractionCache:
    """Empty extraction-cache adapter; D13D executed payloads carry no fingerprints."""

    def clear(self) -> None:
        return None

    def invalidate_by_content(self, fingerprint: str) -> int:
        return 0

    def invalidate_by_event(self, event_id: str) -> int:
        return 0


def build_forget_fts_consumer(observer: D13DForgetFtsObserver) -> tuple:
    """Build the formal forget consumer wired to this FTS deletion port."""
    digest_key_id = "d9d-internal"
    digest_key = b"kylin-memory-d9d-internal"
    provider = D13DForgetFtsDeletionProvider(
        observer,
        digest_key_id=digest_key_id,
        digest_key=digest_key,
    )
    embedding_service = EmbeddingService(provider=_ValidationNoEmbeddingProvider())
    embedding_service.set_cache_invalidator(_ValidationNoExtractionCache())
    consumer = build_forget_consumer(
        embedding_service,
        vector_provider=provider,
        digest_key_id=digest_key_id,
        digest_key=digest_key,
    )
    return consumer, embedding_service


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
