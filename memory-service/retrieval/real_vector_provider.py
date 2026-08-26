"""真实 Vector SDK 桥（V006/D5-B）：通过 vector_cli 子进程做 JSON 往返。

本模块只负责把 SDK 操作翻译成子进程 JSON 调用，并把命中映射为 RetrievalHit；
SDK 错误码在此只做透传（结构化错误映射见 vector_sdk_errors.map_sdk_status）。
不依赖 pybind11 / python3-dev，只需一个已编译的 vector_cli 可执行文件。
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Optional

from retrieval.contracts import Channel, RetrievalHit, ScoreSemantics


class VectorCliError(RuntimeError):
    """vector_cli 执行失败或返回错误状态。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"vector_cli error code={code}: {message}")
        self.code = code
        self.message = message


class VectorCliClient:
    """vector_cli 子进程客户端。"""

    def __init__(self, cli_path: str = "vector_cli") -> None:
        self.cli_path = cli_path

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

    def insert(self, name: str, ids: list[int], vectors: list[list[float]]) -> dict:
        result = self._run("insert", name, stdin=json.dumps({"ids": ids, "vectors": vectors}))
        self._require_ok(result)
        return result

    def drop_collection(self, name: str) -> dict:
        result = self._run("drop_collection", name)
        # drop 已不存在的 collection 是幂等成功（已经是目标状态），不视为错误。
        if not result.get("ok") and result.get("code") == 1002 and "not found" in result.get("message", "").lower():
            return result
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
        now: Optional[datetime] = None,
    ) -> list[RetrievalHit]:
        """执行向量检索，返回 1 起始 rank 的 RetrievalHit。"""
        now = now or datetime.now(timezone.utc)
        result = self._run(
            "search", name, str(top_n), str(timeout), stdin=json.dumps({"vector": vector})
        )
        self._require_ok(result)
        hits: list[RetrievalHit] = []
        for rank, item in enumerate(result.get("hits", []), 1):
            hits.append(
                RetrievalHit(
                    memory_id=str(item["id"]),
                    version_id="v1",
                    user_id=user_id,
                    channel=Channel.VECTOR,
                    rank=rank,
                    raw_score=float(item["score"]),
                    score_semantics=ScoreSemantics.SDK_SCORE_UNVERIFIED,
                    provider="vector_cli",
                    retrieved_at=now,
                    filter_fingerprint="hmac-sha256:k1:" + "a" * 64,
                )
            )
        return hits
