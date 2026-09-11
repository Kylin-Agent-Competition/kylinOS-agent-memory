from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

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

    def fail_writer(rowid, pref, generation):
        calls.append(
            (rowid, pref["value"], generation)
        )
        return False

    last_rowid, retry = bridge.process_rows(
        10,
        rows,
        writer=fail_writer,
    )
    assert last_rowid == 11
    assert retry is True
    assert calls == [(12, "Rust", 0)]


def test_bridge_advances_preference_row_only_after_success():
    bridge = _load("host_memory_bridge_success_rc", BRIDGE_DIR / "host_memory_bridge.py")
    rows = [{"rowid": 21, "text": "请记住：项目偏好语言=C++"}]
    last_rowid, retry = bridge.process_rows(
        20,
        rows,
        writer=lambda _rowid, _pref, _generation: True,
    )
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
    bridge.save_cursor(123, 4, "10:20")
    assert bridge.load_cursor() == {
        "rowid": 123,
        "generation": 4,
        "db_identity": "10:20",
    }
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



def test_bridge_legacy_integer_cursor_is_backward_compatible(
    tmp_path,
):
    bridge = _load(
        "host_memory_bridge_legacy_cursor_rc",
        BRIDGE_DIR / "host_memory_bridge.py",
    )
    bridge.CURSOR_PATH = tmp_path / "bridge.cursor"
    bridge.CURSOR_PATH.write_text(
        "77\n",
        encoding="ascii",
    )

    assert bridge.load_cursor() == {
        "rowid": 77,
        "generation": 0,
        "db_identity": None,
    }


def test_bridge_detects_runtime_db_clear(
    tmp_path,
):
    bridge = _load(
        "host_memory_bridge_runtime_clear_rc",
        BRIDGE_DIR / "host_memory_bridge.py",
    )

    db = tmp_path / "chat.db"

    con = sqlite3.connect(db)
    con.execute("CREATE TABLE RECORD(message TEXT)")

    for i in range(3):
        con.execute(
            "INSERT INTO RECORD(message) VALUES(?)",
            (
                json.dumps(
                    {
                        "author": "Bot",
                        "message": f"old-{i}",
                    }
                ),
            ),
        )

    con.commit()
    con.close()

    bridge.DB_PATH = db
    old_identity = bridge.current_db_identity()

    con = sqlite3.connect(db)
    con.execute("DELETE FROM RECORD")
    con.execute(
        "INSERT INTO RECORD(message) VALUES(?)",
        (
            json.dumps(
                {
                    "author": "User",
                    "message": (
                        "请记住：项目偏好语言=Rust"
                    ),
                },
                ensure_ascii=False,
            ),
        ),
    )
    con.commit()
    con.close()

    (
        rowid,
        generation,
        identity,
        reason,
    ) = bridge.refresh_cursor_for_db(
        3,
        0,
        old_identity,
    )

    assert reason == "rowid-regressed"
    assert rowid == 0
    assert generation == 1
    assert identity == old_identity

    rows, high = bridge.read_new_user_rows(
        0,
        expected_identity=identity,
    )

    calls = []

    def writer(new_rowid, pref, new_generation):
        calls.append(
            (
                new_rowid,
                pref["value"],
                new_generation,
            )
        )
        return True

    last, retry = bridge.process_rows(
        0,
        rows,
        writer=writer,
        generation=generation,
    )

    assert retry is False
    assert max(last, high) == 1
    assert calls == [(1, "Rust", 1)]


def test_bridge_detects_runtime_db_file_replacement(
    tmp_path,
):
    bridge = _load(
        "host_memory_bridge_runtime_replace_rc",
        BRIDGE_DIR / "host_memory_bridge.py",
    )

    db = tmp_path / "chat.db"

    con = sqlite3.connect(db)
    con.execute("CREATE TABLE RECORD(message TEXT)")
    con.execute(
        "INSERT INTO RECORD(message) VALUES(?)",
        (
            json.dumps(
                {
                    "author": "Bot",
                    "message": "old",
                }
            ),
        ),
    )
    con.commit()
    con.close()

    bridge.DB_PATH = db
    old_identity = bridge.current_db_identity()

    replacement = tmp_path / "replacement.db"

    con = sqlite3.connect(replacement)
    con.execute("CREATE TABLE RECORD(message TEXT)")
    con.execute(
        "INSERT INTO RECORD(message) VALUES(?)",
        (
            json.dumps(
                {
                    "author": "Bot",
                    "message": "replacement-history",
                }
            ),
        ),
    )
    con.commit()
    con.close()

    os.replace(replacement, db)

    (
        rowid,
        generation,
        new_identity,
        reason,
    ) = bridge.refresh_cursor_for_db(
        1,
        5,
        old_identity,
    )

    assert reason == "db-replaced"
    assert rowid == 1
    assert generation == 6
    assert new_identity != old_identity

    # Replacement history is not backfilled.
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO RECORD(message) VALUES(?)",
        (
            json.dumps(
                {
                    "author": "User",
                    "message": (
                        "请记住：项目偏好语言=Go"
                    ),
                },
                ensure_ascii=False,
            ),
        ),
    )
    con.commit()
    con.close()

    rows, high = bridge.read_new_user_rows(
        1,
        expected_identity=new_identity,
    )

    assert high == 2
    assert [row["rowid"] for row in rows] == [2]


def test_bridge_generation_scopes_idempotency_and_evidence_ids(
    monkeypatch,
):
    bridge = _load(
        "host_memory_bridge_generation_id_rc",
        BRIDGE_DIR / "host_memory_bridge.py",
    )

    captured = []

    def fake_run(cmd, **_kwargs):
        captured.append(cmd)
        return SimpleNamespace(
            returncode=0,
            stdout='{"status":"ok"}',
            stderr="",
        )

    monkeypatch.setattr(
        bridge.subprocess,
        "run",
        fake_run,
    )

    pref = {
        "key": "project_language",
        "scope": "topic",
        "value": "Rust",
    }

    assert bridge.write_preference(
        12,
        pref,
        generation=0,
    )

    assert bridge.write_preference(
        12,
        pref,
        generation=3,
    )

    legacy_payload = json.loads(captured[0][3])
    assert legacy_payload["evidence_event_ids"] == [
        "kylin-aiassistant-chat-record-12"
    ]
    assert (
        captured[0][4]
        == "host-chat-pref-12-project_language"
    )

    generation_payload = json.loads(captured[1][3])
    assert generation_payload["evidence_event_ids"] == [
        "kylin-aiassistant-chat-g3-record-12"
    ]
    assert (
        captured[1][4]
        == "host-chat-pref-g3-12-project_language"
    )


def test_uninstall_discards_transaction_backups_after_success():
    text = (BRIDGE_DIR / "uninstall_host_integration_rc.sh").read_text(encoding="utf-8")
    assert 'rm -rf "$STATE_DIR"' in text
    assert "active-context.txt" in text


def test_ipc_client_uses_xdg_runtime_dir_by_default(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/kylin-runtime-test")
    ipc = _load("ipc_call_xdg_rc", BRIDGE_DIR / "ipc_call.py")
    assert ipc.DEFAULT_SOCKET == "/tmp/kylin-runtime-test/kylin-memory/memory.sock"


def test_prechat_hook_real_missing_downstream_symbol_is_abi_fail_closed(
    tmp_path,
):
    import os
    import subprocess

    hook_src = (
        ROOT
        / "prechat-hook"
        / "memory_prechat_final.cpp"
    )
    hook_so = tmp_path / "libmemory-prechat-test.so"
    harness_src = tmp_path / "missing_downstream.cpp"
    harness_bin = tmp_path / "missing-downstream"
    log_path = tmp_path / "prechat.log"

    symbol = (
        "_ZN4kyai9assistant11OsAssistant9chatAsyncERK"
        "NSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE"
    )

    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-shared",
            "-fPIC",
            str(hook_src),
            "-ldl",
            "-o",
            str(hook_so),
        ],
        check=True,
    )

    harness_src.write_text(
        r'''
#include <dlfcn.h>
#include <string>

int main(int argc, char** argv) {
    if (argc != 2) return 10;

    void* handle = dlopen(
        argv[1],
        RTLD_NOW | RTLD_GLOBAL
    );
    if (!handle) return 11;

    const char* symbol =
        "_ZN4kyai9assistant11OsAssistant9chatAsyncERK"
        "NSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE";

    using Fn = void (*)(void*, const std::string&);

    auto fn = reinterpret_cast<Fn>(
        dlsym(handle, symbol)
    );
    if (!fn) return 12;

    std::string request =
        R"({"content":"ordinary request"})";

    // No downstream libkyai-assistant is loaded after the hook.
    // RTLD_NEXT must therefore fail safely.
    fn(nullptr, request);

    dlclose(handle);
    return 0;
}
''',
        encoding="utf-8",
    )

    subprocess.run(
        [
            "g++",
            "-std=c++17",
            str(harness_src),
            "-ldl",
            "-o",
            str(harness_bin),
        ],
        check=True,
    )

    env = os.environ.copy()
    env["MEMORY_PRECHAT_LOG"] = str(log_path)
    env["MEMORY_ACTIVE_CONTEXT"] = str(
        tmp_path / "missing-context.txt"
    )

    proc = subprocess.run(
        [
            str(harness_bin),
            str(hook_so),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert proc.returncode == 0

    log = log_path.read_text(encoding="utf-8")
    assert (
        "ABI_FAIL_CLOSED real-chatAsync-not-found"
        in log
    )


def test_installer_preflights_downstream_assistant_chat_abi():
    text = (
        BRIDGE_DIR / "install_host_integration_rc.sh"
    ).read_text(encoding="utf-8")

    assert (
        "/lib/x86_64-linux-gnu/"
        "libkyai-assistant.so.1.0.0"
        in text
    )
    assert "ASSISTANT_CHAT_SYMBOL" in text
    assert "assistant binary identity: PASS" in text
    assert "assistant runtime library identity: PASS" in text
    assert "assistant downstream chatAsync ABI: PASS" in text
    assert "run --command=/usr/bin/sha256sum" in text
    assert 'nm -D --defined-only "$ASSISTANT_RUNTIME_LIB"' in text
    assert "run --command=/usr/bin/nm" not in text

    preflight = text.split(
        "# Compatibility preflight:",
        1,
    )[1].split(
        'mkdir -p "$BIN_DIR"',
        1,
    )[0]

    # Guard against the RC3 generator/paste corruption that produced one
    # physical shell line containing literal "\\n" and patch '+' markers.
    assert r"\n" not in preflight
    assert not any(
        line.startswith("+")
        for line in preflight.splitlines()
    )

    assert text.index(
        'log "assistant downstream chatAsync ABI: PASS"'
    ) < text.index(
        'install -m 0700 "$SELF_DIR/host_memory_bridge.py"'
    )
