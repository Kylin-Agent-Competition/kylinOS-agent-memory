"""D8-B：麒麟 E2E 脚本的 Knowledge 索引输入契约。

真实 Vector Engine 仍由目标麒麟 L2 验证；本测试锁定两条脚本在进入宿主前不会因
缺失 KnowledgeIndexMetadata 而被融合层 fail-closed。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from retrieval.contracts import ObjectType

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str) -> ModuleType:
    path = REPO_ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"d8b_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("script_name", "expected_memory_ids"),
    [
        ("w2_service_fault_e2e.py", {"mem-a", "mem-b"}),
        ("v006_e2e_demo.py", {"1", "2", "3"}),
    ],
)
def test_e2e_knowledge_truth_and_vector_metadata_stay_aligned(
    script_name: str,
    expected_memory_ids: set[str],
) -> None:
    module = _load_script(script_name)
    truth = module.build_truth()
    records = list(truth.values())

    assert {record.memory_id for record in records} == expected_memory_ids
    assert all(record.object_type is ObjectType.KNOWLEDGE for record in records)
    assert all(record.knowledge is not None for record in records)

    fields = module.knowledge_index_fields(records)
    assert fields["object_types"] == ["knowledge"] * len(records)
    assert len(fields["knowledge_types"]) == len(records)
    assert len(fields["primary_categories"]) == len(records)
    assert len(fields["source_event_ids"]) == len(records)
    assert all(fields["source_event_ids"])
