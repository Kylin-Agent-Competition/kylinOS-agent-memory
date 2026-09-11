#!/usr/bin/env python3
"""Validated compatibility adapter: Kylin AI Assistant Chat DB -> preference IPC.

This adapter intentionally extracts only a very small explicit project-language
preference set. It is an RC/host-integration bridge, not a replacement for the
repository's general event.ingest + extraction pipeline.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_PATH = Path(
    os.environ.get(
        "KYLIN_AIASSISTANT_DB",
        str(Path.home() / ".config/kylin-aiassistant/kylin_aiassistant_database.db"),
    )
).expanduser()
IPC_CALL = Path(os.environ.get("KYLIN_MEMORY_IPC_CLIENT", str(HERE / "ipc_call.py"))).expanduser()
USER_ID = os.environ.get("KYLIN_MEMORY_USER_ID", "local-user")
POLL_INTERVAL = float(os.environ.get("KYLIN_MEMORY_BRIDGE_POLL", "0.5"))
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))).expanduser()
CURSOR_PATH = Path(
    os.environ.get(
        "KYLIN_MEMORY_BRIDGE_CURSOR",
        str(STATE_HOME / "kylin-memory/host-integration/bridge.cursor"),
    )
).expanduser()


def _connect_ro() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def current_max_rowid() -> int:
    con = _connect_ro()
    try:
        return int(con.execute("SELECT COALESCE(MAX(rowid), 0) FROM RECORD").fetchone()[0])
    finally:
        con.close()


def read_new_user_rows(after_rowid: int) -> tuple[list[dict], int]:
    """Read one ordered DB batch and return user rows plus its safe high watermark.

    The high watermark is taken from the same SQLite result set, so when every
    relevant user row in the batch has been acknowledged we can advance past Bot
    and malformed rows without a second-query race that could skip a new user row.
    """
    con = _connect_ro()
    try:
        rows = con.execute(
            """
            SELECT rowid, message
            FROM RECORD
            WHERE rowid > ?
            ORDER BY rowid ASC
            """,
            (after_rowid,),
        ).fetchall()
    finally:
        con.close()

    high_watermark = after_rowid
    result = []
    for rowid, raw in rows:
        rowid = int(rowid)
        high_watermark = max(high_watermark, rowid)
        try:
            obj = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if obj.get("author") != "User":
            continue
        text = obj.get("message")
        if not isinstance(text, str) or not text.strip():
            continue
        result.append({"rowid": rowid, "text": text.strip()})
    return result, high_watermark


def extract_preferences(text: str) -> list[dict]:
    patterns = [
        r"项目(?:语言偏好|偏好语言)\s*[=：:]\s*(Python|C\+\+|Java|Rust|Go)",
        r"(?:以后|之后).{0,15}(?:这个项目|项目).{0,15}(?:用|使用)\s*(Python|C\+\+|Java|Rust|Go)",
        r"(?:请记住|记住).{0,20}(?:用|使用)\s*(Python|C\+\+|Java|Rust|Go)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1)
        matched_text = match.group(0)
        if re.search(
            rf"(?:不要|别|不再|禁止).{{0,4}}(?:用|使用)\s*{re.escape(raw)}",
            matched_text,
            re.IGNORECASE,
        ):
            continue
        value = {
            "python": "Python",
            "c++": "C++",
            "java": "Java",
            "rust": "Rust",
            "go": "Go",
        }.get(raw.lower(), raw)
        return [{"key": "project_language", "scope": "topic", "value": value}]
    return []


def write_preference(rowid: int, pref: dict) -> bool:
    payload = {
        "user_id": USER_ID,
        "preference_key": pref["key"],
        "preference_scope": pref["scope"],
        "preference_value": pref["value"],
        "is_temporary": False,
        "should_persist": True,
        "evidence_event_ids": [f"kylin-aiassistant-chat-record-{rowid}"],
    }
    idem = f"host-chat-pref-{rowid}-{pref['key']}"
    cmd = [
        sys.executable,
        str(IPC_CALL),
        "preference.create",
        json.dumps(payload, ensure_ascii=False),
        idem,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        print(f"[bridge] ERROR rowid={rowid}: IPC timeout", flush=True)
        return False

    if proc.returncode != 0:
        print(f"[bridge] ERROR rowid={rowid} rc={proc.returncode}", flush=True)
        if proc.stderr.strip():
            print(proc.stderr.strip(), flush=True)
        return False

    try:
        response = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"[bridge] ERROR rowid={rowid}: malformed IPC response", flush=True)
        return False
    if response.get("status") != "ok":
        print(f"[bridge] ERROR rowid={rowid}: IPC status={response.get('status')}", flush=True)
        return False

    print(f"[bridge] STORED rowid={rowid} key={pref['key']}", flush=True)
    return True


def process_rows(last_rowid: int, rows: list[dict], writer=write_preference) -> tuple[int, bool]:
    """Process rows in order without acknowledging a preference row before IPC succeeds.

    Returns ``(last_rowid, retry_required)``. A failed preference write leaves
    that row unacknowledged so the next poll retries it with the same idempotency
    key instead of silently losing the memory.
    """
    for row in rows:
        prefs = extract_preferences(row["text"])
        if not prefs:
            last_rowid = max(last_rowid, row["rowid"])
            continue

        if not all(writer(row["rowid"], pref) for pref in prefs):
            print(f"[bridge] RETRY rowid={row['rowid']} after IPC recovery", flush=True)
            return last_rowid, True

        last_rowid = max(last_rowid, row["rowid"])

    return last_rowid, False



def load_cursor() -> int | None:
    try:
        raw = CURSOR_PATH.read_text(encoding="ascii").strip()
        value = int(raw)
        return value if value >= 0 else None
    except (OSError, ValueError):
        return None


def save_cursor(rowid: int) -> None:
    CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(CURSOR_PATH.parent, 0o700)
    except OSError:
        pass
    tmp = CURSOR_PATH.with_name(CURSOR_PATH.name + ".tmp")
    tmp.write_text(f"{int(rowid)}\n", encoding="ascii")
    os.chmod(tmp, 0o600)
    os.replace(tmp, CURSOR_PATH)

def wait_for_chat_db_tail() -> int:
    """Wait for the assistant DB at login, then start at its current tail."""
    announced = False
    while True:
        try:
            return current_max_rowid()
        except (OSError, sqlite3.Error):
            if not announced:
                print(f"[bridge] waiting for Chat DB: {DB_PATH}", flush=True)
                announced = True
            time.sleep(1)


def main() -> None:
    print("==============================================", flush=True)
    print(" Kylin AI Assistant -> Memory Service Bridge", flush=True)
    print("==============================================", flush=True)
    print(f"[bridge] Chat DB : {DB_PATH}", flush=True)
    print(f"[bridge] IPC     : {IPC_CALL}", flush=True)
    print(f"[bridge] user_id : {USER_ID}", flush=True)

    if not IPC_CALL.exists():
        raise SystemExit(f"[bridge] FAIL: IPC client not found: {IPC_CALL}")

    # First install deliberately starts at the current DB tail (no historical
    # backfill). After that, persist the acknowledged row cursor so a bridge
    # restart cannot silently lose a preference that arrived while IPC was down.
    tail = wait_for_chat_db_tail()
    saved_cursor = load_cursor()
    if saved_cursor is None:
        last_rowid = tail
        save_cursor(last_rowid)
        cursor_mode = "new-tail"
    elif saved_cursor > tail:
        # The Assistant DB was replaced/reset. A cursor beyond its current tail
        # would otherwise stall forever, so re-baseline to the new DB tail.
        last_rowid = tail
        save_cursor(last_rowid)
        cursor_mode = "db-reset-tail"
    else:
        last_rowid = saved_cursor
        cursor_mode = "resume"
    print(
        f"[bridge] starting_after_rowid={last_rowid} cursor_mode={cursor_mode}",
        flush=True,
    )

    while True:
        try:
            rows, high_watermark = read_new_user_rows(last_rowid)
            new_last_rowid, retry_required = process_rows(last_rowid, rows)
            if not retry_required:
                # Safe because high_watermark came from the same fetched batch.
                new_last_rowid = max(new_last_rowid, high_watermark)
            if new_last_rowid != last_rowid:
                save_cursor(new_last_rowid)
                last_rowid = new_last_rowid
            time.sleep(1 if retry_required else POLL_INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as exc:  # keep watcher alive; do not expose message content
            print(f"[bridge] ERROR {type(exc).__name__}: {exc}", flush=True)
            time.sleep(1)


if __name__ == "__main__":
    main()
