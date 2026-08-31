"""真实 Vector SDK 桥（V006/D5-B）：通过 vector_cli 子进程做 JSON 往返。

本模块只负责把 SDK 操作翻译成子进程 JSON 调用，并把命中映射为 RetrievalHit；
SDK 错误码在此只做透传（结构化错误映射见 vector_sdk_errors.map_sdk_status）。
不依赖 pybind11 / python3-dev，只需一个已编译的 vector_cli 可执行文件。
"""

from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime, timezone
from typing import Optional

from retrieval.contracts import Channel, RetrievalFilter, RetrievalHit, ScoreSemantics


class VectorCliError(RuntimeError):
    """vector_cli 执行失败或返回错误状态。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"vector_cli error code={code}: {message}")
        self.code = code
        self.message = message


class VectorCliClient:
    """vector_cli 子进程客户端。"""

    def __init__(self, cli_path: str = "vector_cli", *, expected_dimension: Optional[int] = None) -> None:
        if expected_dimension is not None and (
            not isinstance(expected_dimension, int)
            or isinstance(expected_dimension, bool)
            or expected_dimension <= 0
        ):
            raise ValueError("expected_dimension 必须是正整数")
        self.cli_path = cli_path
        self.expected_dimension = expected_dimension

    def _run(self, *args: str, stdin: Optional[str] = None) -> dict:
        proc = subprocess.run(
            [self.cli_path, *args],
            input=stdin,
            text=True,
            capture_output=True,
            timeout=120,
        )
        text = (proc.stdout or "").strip()
        # SDK 连接重试日志会污染 stdout；vector_cli 的协议 JSON 是最后一行。
        # 从最后一行往前找第一个能解析为 dict 的行，忽略 SDK 的 WARN/ERROR 噪音。
        result: Optional[dict] = None
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                result = candidate
                break
        if proc.returncode != 0:
            # 非零退出时优先保留 stdout 中的结构化错误（如连接失败 code=3），
            # 否则回退到 stderr。
            if result is not None and result.get("ok") is False:
                raise VectorCliError(int(result.get("code", -1)), result.get("message", ""))
            raise VectorCliError(-1, proc.stderr.strip() or "exit " + str(proc.returncode))
        if result is None:
            return {}
        return result

    def _require_ok(self, result: dict) -> None:
        if not result.get("ok"):
            raise VectorCliError(int(result.get("code", -1)), result.get("message", ""))

    def create_collection(self, name: str, dim: int) -> dict:
        result = self._run("create_collection", name, str(dim))
        self._require_ok(result)
        return result

    def insert(
        self,
        name: str,
        ids: list[int],
        vectors: list[list[float]],
        *,
        user_ids: list[str],
        version_ids: list[str],
        scene_ids: list[str],
        memory_statuses: list[str],
        deleted_flags: list[bool],
        object_types: Optional[list[str]] = None,
        knowledge_types: Optional[list[str]] = None,
        primary_categories: Optional[list[str]] = None,
        source_event_ids: Optional[list[str]] = None,
    ) -> dict:
        has_knowledge_metadata = any(
            value is not None
            for value in (
                object_types,
                knowledge_types,
                primary_categories,
                source_event_ids,
            )
        )
        if has_knowledge_metadata:
            object_types = (
                object_types if object_types is not None else ["knowledge"] * len(ids)
            )
            knowledge_types = (
                knowledge_types if knowledge_types is not None else [""] * len(ids)
            )
            primary_categories = (
                primary_categories
                if primary_categories is not None
                else [""] * len(ids)
            )
            source_event_ids = (
                source_event_ids
                if source_event_ids is not None
                else [""] * len(ids)
            )
        if not (
            len(ids)
            == len(vectors)
            == len(user_ids)
            == len(version_ids)
            == len(scene_ids)
            == len(memory_statuses)
            == len(deleted_flags)
        ):
            raise ValueError("ids、vectors 和全部元数据字段必须等长")
        if has_knowledge_metadata and not (
            len(ids)
            == len(object_types)
            == len(knowledge_types)
            == len(primary_categories)
            == len(source_event_ids)
        ):
            raise ValueError("ids、vectors 和全部元数据字段必须等长")
        for vector in vectors:
            if not vector:
                raise ValueError("向量不能为空")
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                for value in vector
            ):
                raise ValueError("向量元素必须是有限实数")
            if self.expected_dimension is not None and len(vector) != self.expected_dimension:
                raise ValueError(f"写入向量维度必须等于 {self.expected_dimension}")
        payload = {
            "ids": ids,
            "vectors": vectors,
            "user_ids": user_ids,
            "version_ids": version_ids,
            "scene_ids": scene_ids,
            "memory_statuses": memory_statuses,
            "deleted_flags": deleted_flags,
        }
        if has_knowledge_metadata:
            payload.update({
                "object_types": object_types,
                "knowledge_types": knowledge_types,
                "primary_categories": primary_categories,
                "source_event_ids": source_event_ids,
            })
        result = self._run(
            "insert",
            name,
            stdin=json.dumps(payload),
        )
        self._require_ok(result)
        return result

    def drop_collection(self, name: str) -> dict:
        result = self._run("drop_collection", name)
        # drop 已不存在的 collection 是幂等成功（已经是目标状态），不视为错误。
        if not result.get("ok") and result.get("code") == 1002 and "not found" in result.get("message", "").lower():
            return result
        self._require_ok(result)
        return result

    def delete(
        self,
        name: str,
        ids: list[int],
        *,
        user_id: str,
        version_ids: list[str],
    ) -> dict:
        """向 Vector CLI 转发已解析的同用户 ID/版本删除对。"""
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("删除用户必须非空")
        if not isinstance(ids, list) or not ids:
            raise ValueError("删除 ID 不能为空")
        if any(
            isinstance(memory_id, bool)
            or not isinstance(memory_id, int)
            or memory_id <= 0
            for memory_id in ids
        ):
            raise ValueError("删除 ID 必须是正整数")
        if not isinstance(version_ids, list) or len(version_ids) != len(ids):
            raise ValueError("版本 ID 必须与删除 ID 一一对应")
        if any(not isinstance(version_id, str) or not version_id for version_id in version_ids):
            raise ValueError("版本 ID 必须非空")
        result = self._run(
            "delete",
            name,
            stdin=json.dumps(
                {
                    "user_id": user_id,
                    "ids": ids,
                    "version_ids": version_ids,
                }
            ),
        )
        self._require_ok(result)
        return result

    def search(
        self,
        name: str,
        vector: list[float],
        top_n: int,
        timeout: int = 5000,
        *,
        user_id: str,
        filter: RetrievalFilter,
        now: Optional[datetime] = None,
    ) -> list[RetrievalHit]:
        """执行向量检索，返回 1 起始 rank 的 RetrievalHit。"""
        now = now or datetime.now(timezone.utc)
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("搜索 user_id 必须非空")
        if not isinstance(top_n, int) or isinstance(top_n, bool) or top_n <= 0:
            raise ValueError("top_n 必须大于 0")
        if not isinstance(vector, list) or not vector:
            raise ValueError("查询向量不能为空")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in vector
        ):
            raise ValueError("查询向量元素必须是有限实数")
        if self.expected_dimension is None:
            raise ValueError("搜索必须配置 expected_dimension")
        if len(vector) != self.expected_dimension:
            raise ValueError(f"查询向量维度必须等于 {self.expected_dimension}")
        if filter.user_id != user_id:
            raise ValueError("RetrievalFilter.user_id 必须与搜索 user_id 一致")
        cli_filter = {
            "user_id": user_id,
            "allowed_scene_ids": sorted(set(filter.scene.allowed_scene_ids)),
            "include_unscoped": filter.scene.include_unscoped,
            "allowed_memory_statuses": sorted(set(filter.allowed_memory_statuses)),
            "exclude_deleted": True,
            "object_types": sorted({value.value for value in filter.object_types}),
        }
        if any(filter.knowledge.model_dump().values()):
            cli_filter.update({
                "knowledge_types": sorted(set(filter.knowledge.knowledge_types)),
                "primary_categories": sorted(
                    set(filter.knowledge.primary_categories)
                ),
                "source_event_ids": sorted(
                    set(filter.knowledge.source_event_ids)
                ),
                "version_ids": sorted(set(filter.knowledge.version_ids)),
            })
        result = self._run(
            "search",
            name,
            str(top_n),
            str(timeout),
            stdin=json.dumps({"vector": vector, "filter": cli_filter}),
        )
        self._require_ok(result)
        raw_hits = result.get("hits", [])
        if not isinstance(raw_hits, list):
            raise VectorCliError(-1, "search response hits must be a list")
        valid_hits: list[tuple[int, str, str, str, float]] = []
        dropped_hit_count = 0
        for raw_rank, item in enumerate(raw_hits, 1):
            if not isinstance(item, dict):
                dropped_hit_count += 1
                continue
            memory_id = item.get("id")
            hit_user_id = item.get("user_id")
            version_id = item.get("version_id")
            score = item.get("score")
            if (
                memory_id is None
                or isinstance(memory_id, bool)
                or not str(memory_id)
                or not isinstance(hit_user_id, str)
                or not hit_user_id
                or hit_user_id != user_id
                or not isinstance(version_id, str)
                or not version_id
                or isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
            ):
                dropped_hit_count += 1
                continue
            valid_hits.append((raw_rank, str(memory_id), version_id, hit_user_id, float(score)))

        diagnostics = {
            "raw_hit_count": len(raw_hits),
            "valid_hit_count": len(valid_hits),
            "dropped_hit_count": dropped_hit_count,
        }
        hits: list[RetrievalHit] = []
        for rank, memory_id, version_id, hit_user_id, score in valid_hits:
            hits.append(
                RetrievalHit(
                    memory_id=memory_id,
                    version_id=version_id,
                    user_id=hit_user_id,
                    channel=Channel.VECTOR,
                    rank=rank,
                    raw_score=score,
                    score_semantics=ScoreSemantics.SDK_SCORE_UNVERIFIED,
                    provider="vector_cli",
                    retrieved_at=now,
                    filter_fingerprint="hmac-sha256:k1:" + "a" * 64,
                    diagnostics=diagnostics,
                )
            )
        return hits
