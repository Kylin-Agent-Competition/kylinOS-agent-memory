"""L1 tests for the D14C read-only runtime precheck observation seam."""

from __future__ import annotations

from evaluation.d14c_runtime_precheck import collect_precheck_observation


SHA = "b" * 64
HEAD = "a" * 40


class _Probe:
    def os_release(self):
        return {"kernel": "6.6.0-kylin", "kylin_release_id": "Kylin V10"}

    def file_identity(self, path):
        return {"path": path, "exists": True, "sha256": SHA, "owner_uid": 1000, "mode": "0755"}

    def process_identity(self, pid):
        return {"pid": pid, "running": True, "owner_uid": 1000, "cmdline_sha256": SHA, "cmdline_length": 31}

    def systemd_show(self, unit):
        return {
            "unit": unit,
            "exit_code": 0,
            "fragment_path": "/home/user/.config/systemd/user/kylin-memory.service",
            "main_pid": 123,
            "active_enter_timestamp": "Mon 2026-09-08 12:00:00 CST",
            "exec_start_sha256": SHA,
            "exec_start_length": 42,
        }

    def path_identity(self, path):
        return {"path": path, "exists": True, "owner_uid": 1000, "mode": "0660"}


def _request():
    return {
        "run_id": "precheck-20260908-01",
        "tested_commit": HEAD,
        "environment_id": "kylin-vm-01",
        "vm": {"name": "Kylin VM", "uuid": "vm-uuid", "snapshot": "clean", "snapshot_uuid": "snapshot-uuid"},
        "ai_assistant": {"path": "/opt/kylin/assistant", "version": "1.0", "pid": 101},
        "memory_client": {"path": "/opt/kylin/memory-client.so", "build_id": "build-1", "pid": 102},
        "memory_service": {"package_path": "/opt/kylin/kylin-memory.deb", "pid": 123, "unit": "kylin-memory.service"},
        "socket_path": "/run/user/1000/kylin-memory.sock",
        "db_path": "/home/user/.local/share/kylin-memory.db",
        "runtime_ids": {"session_id": "s-1", "trace_id": "t-1", "turn_id": "turn-1", "event_id": "event-1", "execution_record_id": "record-1"},
        "command": {"name": "three-component-precheck", "exit_code": 0},
    }


def test_collector_returns_safe_precheck_observation_for_three_components():
    observation = collect_precheck_observation(_request(), probe=_Probe())

    assert observation["schema_version"] == "d14c-runtime-precheck/v1"
    assert observation["status"] == "PRECHECK_OBSERVATION"
    assert observation["formal_dispatch"] == "NOT_STARTED"
    assert observation["vm"] == {
        "name": "Kylin VM",
        "uuid": "vm-uuid",
        "snapshot": "clean",
        "snapshot_uuid": "snapshot-uuid",
        "kernel": "6.6.0-kylin",
        "kylin_release_id": "Kylin V10",
    }
    assert observation["components"]["ai_assistant"]["binary"]["sha256"] == SHA
    assert observation["components"]["memory_client"]["process"]["cmdline_sha256"] == SHA
    assert observation["components"]["memory_service"]["systemd"]["fragment_path"].endswith(".service")
    assert observation["socket"]["exists"] is True
    assert observation["database"]["path"].endswith(".db")
    assert observation["safety"] == {"user_plaintext_recorded": False, "assistant_plaintext_recorded": False}
    assert "cmdline" not in observation["components"]["memory_service"]["systemd"]


def test_collector_keeps_failed_component_as_observation_not_host_verification():
    class FailingProbe(_Probe):
        def systemd_show(self, unit):
            return {"unit": unit, "exit_code": 3, "reason": "unit-inactive"}

    observation = collect_precheck_observation(_request(), probe=FailingProbe())

    assert observation["status"] == "PRECHECK_OBSERVATION"
    assert observation["components"]["memory_service"]["systemd"]["exit_code"] == 3
    assert observation["components"]["memory_service"]["systemd"]["reason"] == "unit-inactive"
    assert "HOST_VERIFIED" not in str(observation)
