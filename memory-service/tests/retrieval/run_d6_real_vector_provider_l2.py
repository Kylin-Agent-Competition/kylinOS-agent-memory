#!/usr/bin/env python3
"""D6-B L2 probe for the public VectorCliClient -> real vector_cli seam."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVICE_ROOT))

from retrieval.contracts import ObjectType, RetrievalFilter, SceneFilter
from retrieval.real_vector_provider import VectorCliClient


NOW = datetime(2026, 8, 26, 0, 0, 0, tzinfo=timezone.utc)


def _filter(user_id: str, *, statuses: list[str], include_unscoped: bool) -> RetrievalFilter:
    return RetrievalFilter(
        user_id=user_id,
        scene=SceneFilter(allowed_scene_ids=["lab"], include_unscoped=include_unscoped),
        object_types=[ObjectType.KNOWLEDGE],
        allowed_memory_statuses=statuses,
        conflict_policy="exclude_unresolved",
        as_of=NOW,
    )


def _assert_hits(name: str, hits: object, expected: list[tuple[str, str, str]]) -> None:
    actual = [(hit.memory_id, hit.version_id, hit.user_id) for hit in hits]  # type: ignore[union-attr]
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected}, got {actual}")
    print(f"D6B_PROVIDER_L2 name={name} result=PASS hits={actual}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", required=True)
    parser.add_argument("--collection", default=f"d6b_provider_l2_{os.getpid()}")
    args = parser.parse_args()
    if not os.path.isabs(args.cli) or not os.access(args.cli, os.X_OK):
        raise ValueError("--cli must be an executable absolute path")
    if not args.collection.startswith("d6b_"):
        raise ValueError("--collection must use the d6b_ prefix")

    client = VectorCliClient(cli_path=args.cli, expected_dimension=2)
    try:
        client.create_collection(args.collection, 2)
        client.insert(
            args.collection,
            [201, 202, 203, 204, 205],
            [[1.0, 0.0], [0.7, 0.3], [1.0, 0.0], [1.0, 0.0], [0.8, 0.2]],
            user_ids=["user-a", "user-a", "user-b", "user-a", "user-a"],
            version_ids=["v1", "v2", "v3", "v4", "v5"],
            scene_ids=["lab", "lab", "lab", "lab", ""],
            memory_statuses=["active", "inactive", "active", "active", "active"],
            deleted_flags=[False, False, False, True, False],
        )
        _assert_hits(
            "typed_filter_forwarding",
            client.search(
                args.collection,
                [1.0, 0.0],
                10,
                user_id="user-a",
                filter=_filter("user-a", statuses=["active"], include_unscoped=True),
                now=NOW,
            ),
            [("201", "v1", "user-a"), ("205", "v5", "user-a")],
        )
        _assert_hits(
            "cross_user_isolation",
            client.search(
                args.collection,
                [1.0, 0.0],
                10,
                user_id="user-b",
                filter=_filter("user-b", statuses=["active"], include_unscoped=False),
                now=NOW,
            ),
            [("203", "v3", "user-b")],
        )
        _assert_hits(
            "inactive_status_filter",
            client.search(
                args.collection,
                [1.0, 0.0],
                10,
                user_id="user-a",
                filter=_filter("user-a", statuses=["inactive"], include_unscoped=False),
                now=NOW,
            ),
            [("202", "v2", "user-a")],
        )
        try:
            client.insert(
                args.collection,
                [999],
                [[]],
                user_ids=["user-a"],
                version_ids=["v-invalid"],
                scene_ids=["lab"],
                memory_statuses=["active"],
                deleted_flags=[False],
            )
        except ValueError as exc:
            if "向量不能为空" not in str(exc):
                raise
            print("D6B_PROVIDER_L2 name=empty_vector_fail_closed result=PASS")
        else:
            raise AssertionError("empty vector must fail before invoking vector_cli")
        try:
            client.search(
                args.collection,
                [1.0, 0.0],
                10,
                user_id="user-a",
                filter=_filter("user-b", statuses=["active"], include_unscoped=False),
                now=NOW,
            )
        except ValueError as exc:
            if "必须与搜索 user_id 一致" not in str(exc):
                raise
            print("D6B_PROVIDER_L2 name=mismatched_filter_user_fail_closed result=PASS")
        else:
            raise AssertionError("mismatched filter user must fail before invoking vector_cli")
    finally:
        client.drop_collection(args.collection)
    print(f"D6B_PROVIDER_L2 result=PASS collection={args.collection} cleanup=complete")


if __name__ == "__main__":
    main()
