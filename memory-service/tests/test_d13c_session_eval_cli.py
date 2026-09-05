"""D13C CLI（scripts/run_d13c_session_eval.py）L1 测试（R4 fail-closed 全链）。

覆盖：读取文件 / JSON 解析 / root 类型 / config 类型 / sessions 类型 /
config 缺失 / sessions 缺失 / 非法状态组合等全部走统一受控异常路径：
exit_code=2、aggregate_metrics=null、fail_closed_reasons != []、stderr 无 traceback。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts" / "run_d13c_session_eval.py"
FIXTURE = REPO_ROOT / "memory-service" / "tests" / "fixtures" / "d13c_smoke_bundle.json"


def _write(tmp_path, name, obj):
    p = tmp_path / name
    if isinstance(obj, str):
        p.write_text(obj, encoding="utf-8")
    else:
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return p


def _run(tmp_path, bundle):
    out = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(CLI), str(bundle), "--output", str(out)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    report = json.loads(out.read_text(encoding="utf-8"))
    return proc, report


def _valid_bundle(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return _write(tmp_path, "valid.json", data)


def test_cli_valid_bundle_exit_0(tmp_path):
    proc, report = _run(tmp_path, _valid_bundle(tmp_path))
    assert proc.returncode == 0
    assert report["aggregate_metrics"] is not None
    assert report["fail_closed_reasons"] == []
    assert "Traceback" not in proc.stderr


def test_cli_missing_file_fail_closed(tmp_path):
    proc, report = _run(tmp_path, tmp_path / "no-such-bundle.json")
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert report["fail_closed_reasons"]
    assert "Traceback" not in proc.stderr


def test_cli_malformed_json_fail_closed(tmp_path):
    bundle = _write(tmp_path, "bad.json", "{ not json !!")
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert report["fail_closed_reasons"]
    assert "Traceback" not in proc.stderr


def test_cli_root_array_fail_closed(tmp_path):
    bundle = _write(tmp_path, "root_array.json", [])
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert any("ROOT_NOT_OBJECT" in r for r in report["fail_closed_reasons"])
    assert "Traceback" not in proc.stderr


def test_cli_root_string_fail_closed(tmp_path):
    bundle = _write(tmp_path, "root_str.json", json.dumps("abc"))
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert any("ROOT_NOT_OBJECT" in r for r in report["fail_closed_reasons"])


def test_cli_config_array_fail_closed(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["config"] = []
    bundle = _write(tmp_path, "config_array.json", data)
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert any("CONFIG_NOT_OBJECT" in r for r in report["fail_closed_reasons"])


def test_cli_sessions_object_fail_closed(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    data["sessions"] = {}
    bundle = _write(tmp_path, "sessions_obj.json", data)
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert any("SESSIONS_NOT_ARRAY" in r for r in report["fail_closed_reasons"])


def test_cli_config_missing_fail_closed(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del data["config"]
    bundle = _write(tmp_path, "no_config.json", data)
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert any("MISSING_CONFIG" in r for r in report["fail_closed_reasons"])


def test_cli_sessions_missing_fail_closed(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    del data["sessions"]
    bundle = _write(tmp_path, "no_sessions.json", data)
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert any("MISSING_SESSIONS" in r for r in report["fail_closed_reasons"])


def test_cli_invalid_state_combo_fail_closed(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    step = data["sessions"][0]["steps"][0]
    step["response_status"] = "error"
    step["stage_final"] = "ready"
    step["latency_ms"] = 0.0
    bundle = _write(tmp_path, "bad_state.json", data)
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert any("INVALID_INPUT" in r for r in report["fail_closed_reasons"])
    assert "Traceback" not in proc.stderr




def test_cli_no_comparable_pair_exit_2(tmp_path):
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    # 两个不同 scenario 各 1 session → 无 comparable pair → 顶层 fail-closed
    data["sessions"] = [
        {
            "session_id": "only-A",
            "scenario": "scenario_A",
            "injected_context_text": "[CTX] A 内容",
            "steps": json.loads(FIXTURE.read_text(encoding="utf-8"))["sessions"][0]["steps"],
        },
        {
            "session_id": "only-B",
            "scenario": "scenario_B",
            "injected_context_text": "[CTX] B 内容",
            "steps": json.loads(FIXTURE.read_text(encoding="utf-8"))["sessions"][1]["steps"],
        },
    ]
    bundle = _write(tmp_path, "no_pair.json", data)
    proc, report = _run(tmp_path, bundle)
    assert proc.returncode == 2
    assert report["aggregate_metrics"] is None
    assert any("NO_COMPARABLE_CROSS_SESSION_PAIR" in r for r in report["fail_closed_reasons"])
    assert "Traceback" not in proc.stderr
