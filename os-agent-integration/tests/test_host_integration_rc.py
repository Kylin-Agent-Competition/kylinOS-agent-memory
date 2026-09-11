from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIDGE_DIR = ROOT / "host-memory-bridge"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bridge_explicit_project_language_only():
    bridge = _load("host_memory_bridge_rc", BRIDGE_DIR / "host_memory_bridge.py")
    assert bridge.extract_preferences("请记住：项目偏好语言=Rust")[0]["value"] == "Rust"
    assert bridge.extract_preferences("以后这个项目使用 Python")[0]["value"] == "Python"
    assert bridge.extract_preferences("我今天喝咖啡") == []
    assert bridge.extract_preferences("请记住：不要使用 Python") == []


def test_context_render_is_scoped_and_user_request_wins():
    sync = _load("memory_context_sync_rc", BRIDGE_DIR / "memory_context_sync.py")
    text = sync.render("C++")
    assert "preferred project programming language = C++." in text
    assert "current user request has higher priority" in text
    assert sync.render(None) == ""


def test_sandbox_launcher_execs_untouched_official_binary():
    text = (BRIDGE_DIR / "kylin-memory-aiassistant-launcher").read_text(encoding="utf-8")
    assert 'export LD_PRELOAD="$HOOK"' in text
    assert 'exec /usr/bin/kylin-aiassistant "$@"' in text
    assert "nsenter" not in text
    assert "sudo" not in text


def test_installer_overrides_both_manual_and_autostart_entries():
    text = (BRIDGE_DIR / "install_host_integration_rc.sh").read_text(encoding="utf-8")
    assert "kylin-aiassistant.desktop" in text
    assert "kylin-aiassistant-autostart.desktop" in text
    assert "-- --silence" in text
    assert "99-host-integration-rc.conf" in text


def test_installer_resolves_d14a_launcher_before_systemd_override():
    text = (BRIDGE_DIR / "install_host_integration_rc.sh").read_text(encoding="utf-8")
    assert 'MEMORY_SERVER_LINK="$HOME/.local/bin/kylin-memory-server"' in text
    assert 'readlink -f "$MEMORY_SERVER_LINK"' in text
    assert 'ExecStart=%h/.local/bin/kylin-memory-server' not in text
    assert '"$BASE_MEMORY_SERVER"' in text


def test_bridge_does_not_advance_failed_preference_row():
    bridge = _load("host_memory_bridge_retry_rc", BRIDGE_DIR / "host_memory_bridge.py")
    rows = [
        {"rowid": 11, "text": "普通聊天"},
        {"rowid": 12, "text": "请记住：项目偏好语言=Rust"},
        {"rowid": 13, "text": "请记住：项目偏好语言=Python"},
    ]
    calls = []

    def fail_writer(rowid, pref):
        calls.append((rowid, pref["value"]))
        return False

    last_rowid, retry = bridge.process_rows(10, rows, writer=fail_writer)
    assert last_rowid == 11
    assert retry is True
    assert calls == [(12, "Rust")]


def test_bridge_advances_preference_row_only_after_success():
    bridge = _load("host_memory_bridge_success_rc", BRIDGE_DIR / "host_memory_bridge.py")
    rows = [{"rowid": 21, "text": "请记住：项目偏好语言=C++"}]
    last_rowid, retry = bridge.process_rows(20, rows, writer=lambda _rowid, _pref: True)
    assert last_rowid == 21
    assert retry is False



def test_installer_preflights_exact_assistant_and_installed_hook():
    text = (BRIDGE_DIR / "install_host_integration_rc.sh").read_text(encoding="utf-8")
    assert "86453fc660a47940c26031d87807cc735ea1cfd628a657f34a5c896cb0c7ccf6" in text
    assert "host-integration-install-probe" in text
    assert "installed pre-chat hook did not load inside Kaiming" in text
    assert "Memory Service UDS did not become ready" in text
    assert "preference.list IPC smoke: PASS" in text
    assert "systemctl --user restart kylin-memory-host-bridge.service kylin-memory-context-sync.service" in text


def test_context_sync_accepts_only_canonical_project_languages():
    sync = _load("memory_context_sync_allowlist_rc", BRIDGE_DIR / "memory_context_sync.py")
    assert sync.ALLOWED_LANGUAGES == {"Python", "C++", "Java", "Rust", "Go"}
    assert "rm -rf" not in sync.render("Rust")


def test_bridge_cursor_round_trip(tmp_path):
    bridge = _load("host_memory_bridge_cursor_rc", BRIDGE_DIR / "host_memory_bridge.py")
    bridge.CURSOR_PATH = tmp_path / "bridge.cursor"
    assert bridge.load_cursor() is None
    bridge.save_cursor(123)
    assert bridge.load_cursor() == 123
    assert oct(bridge.CURSOR_PATH.stat().st_mode & 0o777) == "0o600"


def test_bridge_batch_high_watermark_advances_past_non_user_rows(tmp_path):
    bridge = _load("host_memory_bridge_hwm_rc", BRIDGE_DIR / "host_memory_bridge.py")
    db = tmp_path / "chat.db"
    import sqlite3, json
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE RECORD(message TEXT)")
    con.execute(
        "INSERT INTO RECORD(message) VALUES(?)",
        (json.dumps({"author": "Bot", "message": "reply"}),),
    )
    con.execute(
        "INSERT INTO RECORD(message) VALUES(?)",
        (json.dumps({"author": "User", "message": "普通聊天"}, ensure_ascii=False),),
    )
    con.execute(
        "INSERT INTO RECORD(message) VALUES(?)",
        ("not-json",),
    )
    con.commit(); con.close()
    bridge.DB_PATH = db
    rows, high = bridge.read_new_user_rows(0)
    assert high == 3
    assert [r["rowid"] for r in rows] == [2]
    last, retry = bridge.process_rows(0, rows, writer=lambda *_: True)
    assert retry is False
    assert max(last, high) == 3


def test_uninstall_discards_transaction_backups_after_success():
    text = (BRIDGE_DIR / "uninstall_host_integration_rc.sh").read_text(encoding="utf-8")
    assert 'rm -rf "$STATE_DIR"' in text
    assert "active-context.txt" in text


def test_ipc_client_uses_xdg_runtime_dir_by_default(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/kylin-runtime-test")
    ipc = _load("ipc_call_xdg_rc", BRIDGE_DIR / "ipc_call.py")
    assert ipc.DEFAULT_SOCKET == "/tmp/kylin-runtime-test/kylin-memory/memory.sock"
