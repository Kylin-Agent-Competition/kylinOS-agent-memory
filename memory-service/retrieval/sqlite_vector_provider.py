"""D10-B：以 SQLite 真源协调 Vector 删除与后续代次重建。"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from db.schema import (
    memory_entries,
    vector_index_entries,
    vector_index_generations,
    vector_index_receipts,
)
from retrieval.contracts import (
    ProviderResult,
    RetrievalError,
    RetrievalErrorCode,
    Availability,
    EvidenceLevel,
    IndexState,
    IndexStateRequest,
    IndexStatus,
    VectorDeleteRequest,
    VectorDeleteResult,
    VectorRebuildRequest,
    VectorRebuildResult,
    VectorUpsertRequest,
    VectorUpsertRejection,
    VectorUpsertResult,
    ActivationMode,
    Watermark,
    digest_from_canonical,
)
from retrieval.sqlite_vector_snapshot import SqliteVectorSnapshotReader


class SqliteVectorProvider:
    """将已确认的 D 轨请求映射到受控 Vector CLI。"""

    def __init__(
        self,
        engine: Engine,
        *,
        vector_client: Any,
        digest_keys: dict[str, bytes],
        embedding_service: Any | None = None,
        index_text_resolver: Any | None = None,
        dimension: int | None = None,
    ) -> None:
        self._engine = engine
        self._vector_client = vector_client
        self._digest_keys = dict(digest_keys)
        self._embedding_service = embedding_service
        self._index_text_resolver = index_text_resolver or (lambda payload: payload.get("index_text"))
        self._dimension = dimension

    @staticmethod
    def _semantic_payload(request: Any) -> dict[str, Any]:
        payload = request.model_dump(
            mode="json",
            exclude={"request_id", "trace_id", "deadline_at", "payload_hash"},
        )
        if isinstance(request, VectorRebuildRequest):
            payload["scope"].pop("scope_fingerprint", None)
        return payload

    def _validate_payload(self, request: Any) -> RetrievalError | None:
        parts = request.payload_hash.split(":", 2)
        if len(parts) != 3 or parts[0] != "hmac-sha256":
            return self._error(RetrievalErrorCode.CONFLICT, "请求摘要格式不合法")
        key_id = parts[1]
        key = self._digest_keys.get(key_id)
        if key is None:
            return self._error(RetrievalErrorCode.DIGEST_KEY_UNAVAILABLE, "请求摘要密钥不可用")
        actual = digest_from_canonical(key_id, key, self._semantic_payload(request))
        if actual != request.payload_hash:
            return self._error(RetrievalErrorCode.CONFLICT, "请求摘要不匹配")
        if isinstance(request, VectorDeleteRequest) and request.selector.user_id != request.user_id:
            return self._error(RetrievalErrorCode.USER_SCOPE_VIOLATION, "删除选择器用户不匹配")
        return None

    @staticmethod
    def _error(code: RetrievalErrorCode, message: str) -> RetrievalError:
        return RetrievalError(
            code=code,
            message=message,
            retryable=False,
            stage="sqlite_vector",
            provider="sqlite_vector",
        )

    @staticmethod
    def _result(*, request_id: str, started: float, value: Any | None = None,
                error: RetrievalError | None = None) -> ProviderResult[Any]:
        return ProviderResult(
            ok=error is None,
            value=value,
            error=error,
            provider="sqlite_vector",
            request_id=request_id,
            elapsed_ms=max(0, int((time.monotonic() - started) * 1000)),
            completed_at=datetime.now(timezone.utc),
        )

    def upsert(self, request: VectorUpsertRequest) -> ProviderResult[VectorUpsertResult]:
        """把 ``memory.upserted`` 的向量写入真实 Vector collection 并记账。

        SQLite 账本负责代次、用户范围、幂等回执和当前版本；Vector CLI 只负责
        承载可重建的派生向量。外部写入成功后才提交账本，失败时不 ACK 对应
        Outbox 事件，由 Worker 负责重试。
        """
        started = time.monotonic()
        if datetime.now(timezone.utc) >= request.deadline_at:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.DEADLINE_EXCEEDED, "写入截止时间已过"),
            )
        if self._dimension is None or self._dimension <= 0:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.PROVIDER_NOT_READY, "Vector 写入维度未配置"),
            )
        invalid = self._validate_payload(request)
        if invalid is not None:
            return self._result(request_id=request.request_id, started=started, error=invalid)

        scope_id = request.source_watermark.domain.scope_id
        if scope_id != f"user:{request.user_id}":
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.USER_SCOPE_VIOLATION, "写入范围未绑定请求用户"),
            )
        with self._engine.connect() as conn:
            receipt = conn.execute(
                select(
                    vector_index_receipts.c.payload_hash,
                    vector_index_receipts.c.result_json,
                ).where(
                    vector_index_receipts.c.scope_id == scope_id,
                    vector_index_receipts.c.user_id == request.user_id,
                    vector_index_receipts.c.operation == "upsert",
                    vector_index_receipts.c.generation == request.index_generation,
                    vector_index_receipts.c.idempotency_key == request.idempotency_key,
                )
            ).mappings().one_or_none()
        if receipt is not None:
            if receipt["payload_hash"] != request.payload_hash:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.CONFLICT, "幂等键的请求摘要冲突"),
                )
            try:
                replayed = VectorUpsertResult.model_validate(json.loads(receipt["result_json"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR, "写入幂等回执损坏"),
                )
            return self._result(request_id=request.request_id, started=started, value=replayed)

        accepted = []
        rejections: list[VectorUpsertRejection] = []
        for record in request.records:
            if record.user_id != request.user_id:
                rejections.append(VectorUpsertRejection(
                    memory_id=record.memory_id, reason="user_scope_violation"
                ))
                continue
            try:
                numeric_id = int(record.memory_id)
            except (TypeError, ValueError):
                rejections.append(VectorUpsertRejection(
                    memory_id=record.memory_id, reason="memory_id_not_positive_integer"
                ))
                continue
            if numeric_id <= 0 or str(numeric_id) != record.memory_id:
                rejections.append(VectorUpsertRejection(
                    memory_id=record.memory_id, reason="memory_id_not_positive_integer"
                ))
                continue
            if len(record.vector) != self._dimension:
                rejections.append(VectorUpsertRejection(
                    memory_id=record.memory_id, reason="dimension_mismatch"
                ))
                continue
            accepted.append((record, numeric_id))

        with self._engine.connect() as conn:
            generation_row = conn.execute(
                select(
                    vector_index_generations.c.collection_name,
                    vector_index_generations.c.status,
                    vector_index_generations.c.source_watermark,
                ).where(
                    vector_index_generations.c.scope_id == scope_id,
                    vector_index_generations.c.generation == request.index_generation,
                )
            ).mappings().one_or_none()
        collection_name: str
        if generation_row is None:
            # 首个真实 upsert 可为该用户/代次建立空的 serving collection；后续
            # 请求仍必须经过同一 SQLite 代次账本，避免隐式跨用户共享集合。
            collection_name = self._collection_name(scope_id, request.index_generation)
            try:
                self._vector_client.create_collection(collection_name, self._dimension)
            except Exception:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.PROVIDER_UNAVAILABLE, "Vector collection 创建失败"),
                )
            try:
                with self._engine.begin() as conn:
                    conn.execute(
                        update(vector_index_generations)
                        .where(vector_index_generations.c.scope_id == scope_id)
                        .values(is_serving=0)
                    )
                    conn.execute(insert(vector_index_generations).values(
                        scope_id=scope_id,
                        generation=request.index_generation,
                        collection_name=collection_name,
                        status="ready",
                        schema_version="vector-retrieval/v1",
                        source_watermark=json.dumps(request.source_watermark.model_dump(mode="json")),
                        record_count=0,
                        is_serving=1,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        activated_at=datetime.now(timezone.utc).isoformat(),
                    ))
                generation_row = {
                    "collection_name": collection_name,
                    "status": "ready",
                    "source_watermark": json.dumps(request.source_watermark.model_dump(mode="json")),
                }
            except IntegrityError:
                # 另一个进程可能完成了相同代次的注册；复读账本，不重复改变
                # 代次状态。Vector collection 的 create 本身是幂等目标状态。
                with self._engine.connect() as conn:
                    generation_row = conn.execute(
                        select(
                            vector_index_generations.c.collection_name,
                            vector_index_generations.c.status,
                            vector_index_generations.c.source_watermark,
                        ).where(
                            vector_index_generations.c.scope_id == scope_id,
                            vector_index_generations.c.generation == request.index_generation,
                        )
                    ).mappings().one_or_none()
                if generation_row is None:
                    return self._result(
                        request_id=request.request_id,
                        started=started,
                        error=self._error(RetrievalErrorCode.CONFLICT, "Vector 代次注册冲突"),
                    )
        if generation_row["status"] != "ready":
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.PROVIDER_NOT_READY, "目标 Vector 代次不可用"),
            )
        collection_name = str(generation_row["collection_name"])

        if generation_row["source_watermark"] is not None:
            try:
                current = Watermark.model_validate(json.loads(generation_row["source_watermark"]))
                if request.source_watermark.compare(current) < 0:
                    return self._result(
                        request_id=request.request_id,
                        started=started,
                        error=self._error(RetrievalErrorCode.STALE_INDEX, "写入水位落后于当前代次"),
                    )
            except (TypeError, ValueError, json.JSONDecodeError):
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR, "代次水位账本损坏"),
                )

        if accepted:
            records, numeric_ids = zip(*accepted, strict=True)
            try:
                self._vector_client.insert(
                    collection_name,
                    list(numeric_ids),
                    [record.vector for record in records],
                    user_ids=[record.user_id for record in records],
                    version_ids=[record.version_id for record in records],
                    scene_ids=[record.scene_id or "" for record in records],
                    memory_statuses=["active"] * len(records),
                    deleted_flags=[False] * len(records),
                    object_types=[record.object_type.value for record in records],
                    knowledge_types=[
                        record.knowledge.knowledge_type if record.knowledge else ""
                        for record in records
                    ],
                    primary_categories=[
                        record.knowledge.primary_category if record.knowledge and record.knowledge.primary_category else ""
                        for record in records
                    ],
                    source_event_ids=[
                        record.knowledge.source_event_id if record.knowledge else ""
                        for record in records
                    ],
                    deadline_at=request.deadline_at,
                )
            except Exception:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.PROVIDER_UNAVAILABLE, "Vector upsert 失败"),
                )

        value = VectorUpsertResult(
            accepted_count=len(accepted),
            upserted_count=len(accepted),
            unchanged_count=0,
            rejected=rejections,
            index_generation=request.index_generation,
            applied_watermark=request.source_watermark,
            outcome="partial" if rejections else "applied",
        )
        try:
            with self._engine.begin() as conn:
                for record, numeric_id in accepted:
                    conn.execute(
                        update(vector_index_entries)
                        .where(
                            vector_index_entries.c.scope_id == scope_id,
                            vector_index_entries.c.generation == request.index_generation,
                            vector_index_entries.c.user_id == request.user_id,
                            vector_index_entries.c.memory_entry_id == numeric_id,
                        )
                        .values(is_active=0)
                    )
                    conn.execute(
                        delete(vector_index_entries).where(
                            vector_index_entries.c.scope_id == scope_id,
                            vector_index_entries.c.generation == request.index_generation,
                            vector_index_entries.c.user_id == request.user_id,
                            vector_index_entries.c.memory_entry_id == numeric_id,
                            vector_index_entries.c.version_id == record.version_id,
                        )
                    )
                    conn.execute(insert(vector_index_entries).values(
                        scope_id=scope_id,
                        generation=request.index_generation,
                        user_id=request.user_id,
                        memory_entry_id=numeric_id,
                        version_id=record.version_id,
                        is_active=1,
                    ))
                active_count = conn.execute(
                    select(func.count()).select_from(vector_index_entries).where(
                        vector_index_entries.c.scope_id == scope_id,
                        vector_index_entries.c.generation == request.index_generation,
                        vector_index_entries.c.is_active == 1,
                    )
                ).scalar_one()
                conn.execute(
                    update(vector_index_generations)
                    .where(
                        vector_index_generations.c.scope_id == scope_id,
                        vector_index_generations.c.generation == request.index_generation,
                    )
                    .values(
                        source_watermark=json.dumps(request.source_watermark.model_dump(mode="json")),
                        record_count=int(active_count),
                    )
                )
                conn.execute(insert(vector_index_receipts).values(
                    scope_id=scope_id,
                    user_id=request.user_id,
                    operation="upsert",
                    generation=request.index_generation,
                    idempotency_key=request.idempotency_key,
                    payload_hash=request.payload_hash,
                    result_json=json.dumps(value.model_dump(mode="json"), ensure_ascii=False),
                    created_at=datetime.now(timezone.utc).isoformat(),
                ))
        except IntegrityError:
            # Only a concurrent identical idempotency request may win this key.
            with self._engine.connect() as conn:
                concurrent = conn.execute(
                    select(vector_index_receipts.c.payload_hash, vector_index_receipts.c.result_json).where(
                        vector_index_receipts.c.scope_id == scope_id,
                        vector_index_receipts.c.user_id == request.user_id,
                        vector_index_receipts.c.operation == "upsert",
                        vector_index_receipts.c.generation == request.index_generation,
                        vector_index_receipts.c.idempotency_key == request.idempotency_key,
                    )
                ).mappings().one_or_none()
            if concurrent is not None and concurrent["payload_hash"] == request.payload_hash:
                value = VectorUpsertResult.model_validate(json.loads(concurrent["result_json"]))
            else:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.CONFLICT, "写入账本冲突"),
                )
        return self._result(request_id=request.request_id, started=started, value=value)

    def delete(self, request: VectorDeleteRequest) -> ProviderResult[VectorDeleteResult]:
        """按已确认的逻辑 ID/版本删除本代次中的已记账索引项。"""
        started = time.monotonic()
        if datetime.now(timezone.utc) >= request.deadline_at:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.DEADLINE_EXCEEDED, "删除截止时间已过"),
            )
        invalid = self._validate_payload(request)
        if invalid is not None:
            return self._result(request_id=request.request_id, started=started, error=invalid)

        version_ids = request.selector.version_ids
        if version_ids is None or len(version_ids) != len(request.selector.memory_ids):
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(
                    RetrievalErrorCode.INVALID_ARGUMENT,
                    "删除选择器必须提供与记忆 ID 一一对应的版本",
                ),
            )

        pairs: list[tuple[str, int, str]] = []
        for memory_id, version_id in zip(
            request.selector.memory_ids,
            version_ids,
            strict=True,
        ):
            try:
                numeric_id = int(memory_id)
            except (TypeError, ValueError):
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.INVALID_ARGUMENT, "memory_id 必须是十进制 SQLite 主键"),
                )
            if numeric_id <= 0 or str(numeric_id) != memory_id:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.INVALID_ARGUMENT, "memory_id 必须是规范 SQLite 主键"),
                )
            pairs.append((memory_id, numeric_id, version_id))

        scope_id = request.source_watermark.domain.scope_id
        with self._engine.begin() as conn:
            receipt = conn.execute(
                select(
                    vector_index_receipts.c.payload_hash,
                    vector_index_receipts.c.result_json,
                ).where(
                    vector_index_receipts.c.scope_id == scope_id,
                    vector_index_receipts.c.user_id == request.user_id,
                    vector_index_receipts.c.operation == "delete",
                    vector_index_receipts.c.generation == request.index_generation,
                    vector_index_receipts.c.idempotency_key == request.idempotency_key,
                )
            ).mappings().one_or_none()
            if receipt is not None:
                if receipt["payload_hash"] != request.payload_hash:
                    return self._result(
                        request_id=request.request_id,
                        started=started,
                        error=self._error(RetrievalErrorCode.CONFLICT, "幂等键的请求摘要冲突"),
                    )
                try:
                    replayed = VectorDeleteResult.model_validate(json.loads(receipt["result_json"]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    return self._result(
                        request_id=request.request_id,
                        started=started,
                        error=self._error(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR, "删除幂等回执损坏"),
                    )
                return self._result(request_id=request.request_id, started=started, value=replayed)

            generation_row = conn.execute(
                select(
                    vector_index_generations.c.collection_name,
                    vector_index_generations.c.source_watermark,
                )
                .where(
                    vector_index_generations.c.scope_id == scope_id,
                    vector_index_generations.c.generation == request.index_generation,
                    vector_index_generations.c.status == "ready",
                )
            ).mappings().one_or_none()
            if generation_row is None:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.PROVIDER_NOT_READY, "目标 Vector 代次不可用"),
                )
            generation = generation_row["collection_name"]
            if generation_row["source_watermark"] is not None:
                try:
                    current_watermark = Watermark.model_validate(
                        json.loads(generation_row["source_watermark"])
                    )
                    if request.source_watermark.compare(current_watermark) < 0:
                        return self._result(
                            request_id=request.request_id,
                            started=started,
                            error=self._error(RetrievalErrorCode.STALE_INDEX, "删除水位落后于当前代次"),
                        )
                except (TypeError, ValueError, json.JSONDecodeError):
                    return self._result(
                        request_id=request.request_id,
                        started=started,
                        error=self._error(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR, "代次水位账本损坏"),
                    )

            matched: list[tuple[str, int, str]] = []
            not_matched: list[str] = []
            for memory_id, numeric_id, version_id in pairs:
                source_exists = conn.execute(
                    select(memory_entries.c.id).where(
                        memory_entries.c.id == numeric_id,
                        memory_entries.c.user_id == request.user_id,
                    )
                ).scalar_one_or_none()
                ledger_exists = conn.execute(
                    select(vector_index_entries.c.memory_entry_id).where(
                        vector_index_entries.c.scope_id == scope_id,
                        vector_index_entries.c.generation == request.index_generation,
                        vector_index_entries.c.user_id == request.user_id,
                        vector_index_entries.c.memory_entry_id == numeric_id,
                        vector_index_entries.c.version_id == version_id,
                        vector_index_entries.c.is_active == 1,
                    )
                ).scalar_one_or_none()
                if source_exists is None or ledger_exists is None:
                    not_matched.append(memory_id)
                else:
                    matched.append((memory_id, numeric_id, version_id))

            if matched:
                try:
                    self._vector_client.delete(
                        generation,
                        [item[1] for item in matched],
                        user_id=request.user_id,
                        version_ids=[item[2] for item in matched],
                    )
                except Exception:
                    return self._result(
                        request_id=request.request_id,
                        started=started,
                        error=self._error(RetrievalErrorCode.PROVIDER_UNAVAILABLE, "Vector 删除失败"),
                    )
                for _, numeric_id, version_id in matched:
                    conn.execute(
                        update(vector_index_entries)
                        .where(
                            vector_index_entries.c.scope_id == scope_id,
                            vector_index_entries.c.generation == request.index_generation,
                            vector_index_entries.c.user_id == request.user_id,
                            vector_index_entries.c.memory_entry_id == numeric_id,
                            vector_index_entries.c.version_id == version_id,
                        )
                        .values(is_active=0)
                    )
            conn.execute(
                update(vector_index_generations)
                .where(
                    vector_index_generations.c.scope_id == scope_id,
                    vector_index_generations.c.generation == request.index_generation,
                )
                .values(source_watermark=json.dumps(request.source_watermark.model_dump(mode="json")))
            )

            value = VectorDeleteResult(
                matched_count=len(matched),
                deleted_count=len(matched),
                not_matched_ids=not_matched,
                index_generation=request.index_generation,
                applied_watermark=request.source_watermark,
                outcome="applied" if matched else "no_op",
            )
            conn.execute(
                insert(vector_index_receipts).values(
                    scope_id=scope_id,
                    user_id=request.user_id,
                    operation="delete",
                    generation=request.index_generation,
                    idempotency_key=request.idempotency_key,
                    payload_hash=request.payload_hash,
                    result_json=json.dumps(value.model_dump(mode="json"), ensure_ascii=False),
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        return self._result(request_id=request.request_id, started=started, value=value)

    @staticmethod
    def _collection_name(scope_id: str, generation: str) -> str:
        safe_scope = re.sub(r"[^A-Za-z0-9]+", "_", scope_id).strip("_")
        safe_generation = re.sub(r"[^A-Za-z0-9]+", "_", generation).strip("_")
        return f"d10b_{safe_scope}_{safe_generation}"

    def rebuild(self, request: VectorRebuildRequest) -> ProviderResult[VectorRebuildResult]:
        """从 D 轨快照重建新代次，全部验证通过后才更新 serving 路由。"""
        started = time.monotonic()
        if datetime.now(timezone.utc) >= request.deadline_at:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.DEADLINE_EXCEEDED, "重建截止时间已过"),
            )
        invalid = self._validate_payload(request)
        if invalid is not None:
            return self._result(request_id=request.request_id, started=started, error=invalid)
        if request.scope.kind.value != "user" or request.scope.user_id != request.user_id:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.AUTHORIZATION_DENIED, "重建范围未绑定请求用户"),
            )
        authorization = request.scope_authorization
        if authorization.scope_id != request.scope.scope_id or "rebuild" not in authorization.allowed_operations:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.AUTHORIZATION_DENIED, "重建授权范围不足"),
            )
        if datetime.now(timezone.utc) >= authorization.expires_at:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.AUTHORIZATION_EXPIRED, "重建授权已过期"),
            )
        if self._embedding_service is None or self._dimension is None or self._dimension <= 0:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.PROVIDER_NOT_READY, "Embedding 重建依赖未配置"),
            )

        with self._engine.begin() as conn:
            receipt = conn.execute(
                select(
                    vector_index_receipts.c.payload_hash,
                    vector_index_receipts.c.result_json,
                ).where(
                    vector_index_receipts.c.scope_id == request.scope.scope_id,
                    vector_index_receipts.c.user_id == request.user_id,
                    vector_index_receipts.c.operation == "rebuild",
                    vector_index_receipts.c.generation == request.target_generation,
                    vector_index_receipts.c.idempotency_key == request.idempotency_key,
                )
            ).mappings().one_or_none()
            if receipt is not None:
                if receipt["payload_hash"] != request.payload_hash:
                    return self._result(
                        request_id=request.request_id,
                        started=started,
                        error=self._error(RetrievalErrorCode.CONFLICT, "幂等键的请求摘要冲突"),
                    )
                try:
                    replayed = VectorRebuildResult.model_validate(json.loads(receipt["result_json"]))
                except (TypeError, ValueError, json.JSONDecodeError):
                    return self._result(
                        request_id=request.request_id,
                        started=started,
                        error=self._error(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR, "重建幂等回执损坏"),
                    )
                return self._result(request_id=request.request_id, started=started, value=replayed)
            existing_target = conn.execute(
                select(vector_index_generations.c.generation).where(
                    vector_index_generations.c.scope_id == request.scope.scope_id,
                    vector_index_generations.c.generation == request.target_generation,
                )
            ).scalar_one_or_none()
            if existing_target is not None:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.CONFLICT, "目标代次已存在"),
                )
            previous_generation = conn.execute(
                select(vector_index_generations.c.generation).where(
                    vector_index_generations.c.scope_id == request.scope.scope_id,
                    vector_index_generations.c.is_serving == 1,
                )
            ).scalar_one_or_none()
            snapshot = SqliteVectorSnapshotReader(self._index_text_resolver).read(
                conn,
                user_id=request.user_id,
                source_snapshot_id=request.source_snapshot_id,
                source_watermark=request.source_watermark,
            )
            if snapshot.rejections:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.STALE_INDEX, "重建快照含被拒绝记录"),
                )
            key_id = request.payload_hash.split(":", 2)[1]
            record_digest = digest_from_canonical(
                key_id,
                self._digest_keys[key_id],
                [
                    {
                        "memory_entry_id": record.memory_entry_id,
                        "version_id": f"v{record.source_version}",
                        "index_text": record.index_text,
                    }
                    for record in snapshot.records
                ],
            )
            collection_name = self._collection_name(request.scope.scope_id, request.target_generation)
            conn.execute(
                insert(vector_index_generations).values(
                    scope_id=request.scope.scope_id,
                    generation=request.target_generation,
                    collection_name=collection_name,
                    status="building",
                    schema_version=request.schema_version,
                    source_snapshot_id=request.source_snapshot_id,
                    source_watermark=json.dumps(request.source_watermark.model_dump(mode="json")),
                    record_digest=record_digest,
                    record_count=0,
                    is_serving=0,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )

        try:
            embedding_response = self._embedding_service.embed_batch(
                [record.index_text for record in snapshot.records]
            )
            vectors = embedding_response.get("result", {}).get("vectors", []) if embedding_response.get("ok") else []
            if embedding_response.get("degraded") or len(vectors) != len(snapshot.records):
                raise ValueError("Embedding 批量结果不完整")
            values = [item.get("vector") if isinstance(item, dict) else None for item in vectors]
            if any(not isinstance(vector, list) or len(vector) != self._dimension for vector in values):
                raise ValueError("Embedding 向量维度不匹配")
            self._vector_client.create_collection(collection_name, self._dimension)
            if snapshot.records:
                self._vector_client.insert(
                    collection_name,
                    [record.memory_entry_id for record in snapshot.records],
                    values,
                    user_ids=[record.user_id for record in snapshot.records],
                    version_ids=[f"v{record.source_version}" for record in snapshot.records],
                    scene_ids=[""] * len(snapshot.records),
                    memory_statuses=["active"] * len(snapshot.records),
                    deleted_flags=[False] * len(snapshot.records),
                )
        except Exception:
            try:
                self._vector_client.drop_collection(collection_name)
            except Exception:
                pass
            with self._engine.begin() as conn:
                conn.execute(
                    update(vector_index_generations)
                    .where(
                        vector_index_generations.c.scope_id == request.scope.scope_id,
                        vector_index_generations.c.generation == request.target_generation,
                    )
                    .values(status="failed", last_error="重建写入失败")
                )
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.PROVIDER_UNAVAILABLE, "Vector 重建写入失败"),
            )

        with self._engine.begin() as conn:
            conn.execute(
                update(vector_index_generations)
                .where(vector_index_generations.c.scope_id == request.scope.scope_id)
                .values(is_serving=0)
            )
            conn.execute(
                update(vector_index_generations)
                .where(
                    vector_index_generations.c.scope_id == request.scope.scope_id,
                    vector_index_generations.c.generation == request.target_generation,
                )
                .values(
                    status="ready",
                    record_count=len(snapshot.records),
                    is_serving=1,
                    activated_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            for record in snapshot.records:
                conn.execute(
                    insert(vector_index_entries).values(
                        scope_id=request.scope.scope_id,
                        generation=request.target_generation,
                        user_id=record.user_id,
                        memory_entry_id=record.memory_entry_id,
                        version_id=f"v{record.source_version}",
                        is_active=1,
                    )
                )
            value = VectorRebuildResult(
                scope=request.scope,
                target_generation=request.target_generation,
                source_snapshot_id=request.source_snapshot_id,
                source_watermark=request.source_watermark,
                read_count=len(snapshot.records),
                indexed_count=len(snapshot.records),
                rejected_count=0,
                verified=True,
                activated=True,
                activation_mode=ActivationMode.ROUTING_SWITCH,
                previous_generation=previous_generation,
                outcome="applied",
            )
            conn.execute(
                insert(vector_index_receipts).values(
                    scope_id=request.scope.scope_id,
                    user_id=request.user_id,
                    operation="rebuild",
                    generation=request.target_generation,
                    idempotency_key=request.idempotency_key,
                    payload_hash=request.payload_hash,
                    result_json=json.dumps(value.model_dump(mode="json"), ensure_ascii=False),
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        return self._result(request_id=request.request_id, started=started, value=value)

    def get_index_state(self, request: IndexStateRequest) -> ProviderResult[IndexState]:
        """从 SQLite 账本读取 serving 代次状态，不触发任何外部操作。"""
        started = time.monotonic()
        if datetime.now(timezone.utc) >= request.deadline_at:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.DEADLINE_EXCEEDED, "状态读取截止时间已过"),
            )
        authorization = request.scope_authorization
        if authorization.scope_id != request.scope.scope_id or "get_index_state" not in authorization.allowed_operations:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.AUTHORIZATION_DENIED, "状态读取授权范围不足"),
            )
        if datetime.now(timezone.utc) >= authorization.expires_at:
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.AUTHORIZATION_EXPIRED, "状态读取授权已过期"),
            )

        with self._engine.connect() as conn:
            row = conn.execute(
                select(vector_index_generations).where(
                    vector_index_generations.c.scope_id == request.scope.scope_id,
                    vector_index_generations.c.is_serving == 1,
                )
            ).mappings().one_or_none()
        if row is None:
            state = IndexState(
                provider="sqlite_vector",
                scope=request.scope,
                status=IndexStatus.EMPTY,
                is_queryable=False,
                schema_version="unknown",
                required_watermark=request.required_watermark,
                last_checked_at=datetime.now(timezone.utc),
                evidence_level=EvidenceLevel.UNTESTED,
                availability=Availability.AVAILABLE,
            )
            return self._result(request_id=request.request_id, started=started, value=state)

        try:
            applied_watermark = Watermark.model_validate(json.loads(row["source_watermark"]))
            status = IndexStatus(row["status"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._result(
                request_id=request.request_id,
                started=started,
                error=self._error(RetrievalErrorCode.PROVIDER_PROTOCOL_ERROR, "Vector 代次账本损坏"),
            )
        if request.required_watermark is not None:
            try:
                if applied_watermark.compare(request.required_watermark) < 0:
                    status = IndexStatus.STALE
            except ValueError:
                return self._result(
                    request_id=request.request_id,
                    started=started,
                    error=self._error(RetrievalErrorCode.INVALID_ARGUMENT, "请求水位与代次水位不可比较"),
                )
        state = IndexState(
            provider="sqlite_vector",
            scope=request.scope,
            status=status,
            is_queryable=status is IndexStatus.READY,
            schema_version=row["schema_version"] or "unknown",
            serving_generation=row["generation"],
            source_snapshot_id=row["source_snapshot_id"],
            applied_watermark=applied_watermark,
            required_watermark=request.required_watermark,
            record_count=int(row["record_count"]),
            last_checked_at=datetime.now(timezone.utc),
            evidence_level=EvidenceLevel.UNTESTED,
            availability=Availability.AVAILABLE,
        )
        return self._result(request_id=request.request_id, started=started, value=state)
