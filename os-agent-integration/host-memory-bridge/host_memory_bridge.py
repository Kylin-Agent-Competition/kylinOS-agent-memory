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


class ChatDbChanged(RuntimeError):
    """Assistant Chat DB changed during a polling operation."""


def _connect_ro() -> sqlite3.Connection:
    uri = DB_PATH.resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def current_max_rowid() -> int:
    con = _connect_ro()
    try:
        return int(
            con.execute(
                "SELECT COALESCE(MAX(rowid), 0) FROM RECORD"
            ).fetchone()[0]
        )
    finally:
        con.close()


def current_db_identity() -> str:
    """Stable identity for the current Chat DB file."""
    st = DB_PATH.stat()
    return f"{st.st_dev}:{st.st_ino}"


def current_db_snapshot() -> tuple[int, str]:
    """Return a stable (tail, identity) snapshot."""
    identity_before = current_db_identity()
    tail = current_max_rowid()
    identity_after = current_db_identity()

    if identity_before != identity_after:
        raise ChatDbChanged("Chat DB changed while reading tail")

    return tail, identity_after


def read_new_user_rows(
    after_rowid: int,
    expected_identity: str | None = None,
) -> tuple[list[dict], int]:
    """Read one ordered DB batch and return user rows plus safe high watermark."""

    identity_before = current_db_identity()

    if (
        expected_identity is not None
        and identity_before != expected_identity
    ):
        raise ChatDbChanged(
            "Chat DB identity changed before batch read"
        )

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

    identity_after = current_db_identity()
    if identity_before != identity_after:
        raise ChatDbChanged(
            "Chat DB changed during batch read"
        )

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

        message = obj.get("message")
        if not isinstance(message, str) or not message.strip():
            continue

        result.append(
            {
                "rowid": rowid,
                "text": message.strip(),
            }
        )

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


def write_preference(
    rowid: int,
    pref: dict,
    generation: int = 0,
) -> bool:
    # Keep generation 0 identifiers backward compatible with RC2 so an
    # interrupted pre-upgrade write cannot be duplicated during migration.
    if generation == 0:
        evidence_event_id = (
            f"kylin-aiassistant-chat-record-{rowid}"
        )
        idem = f"host-chat-pref-{rowid}-{pref['key']}"
    else:
        evidence_event_id = (
            f"kylin-aiassistant-chat-g{generation}-record-{rowid}"
        )
        idem = (
            f"host-chat-pref-g{generation}-{rowid}-{pref['key']}"
        )

    payload = {
        "user_id": USER_ID,
        "preference_key": pref["key"],
        "preference_scope": pref["scope"],
        "preference_value": pref["value"],
        "is_temporary": False,
        "should_persist": True,
        "evidence_event_ids": [evidence_event_id],
    }

    cmd = [
        sys.executable,
        str(IPC_CALL),
        "preference.create",
        json.dumps(payload, ensure_ascii=False),
        idem,
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[bridge] ERROR rowid={rowid}: IPC timeout",
            flush=True,
        )
        return False

    if proc.returncode != 0:
        print(
            f"[bridge] ERROR rowid={rowid} rc={proc.returncode}",
            flush=True,
        )
        if proc.stderr.strip():
            print(proc.stderr.strip(), flush=True)
        return False

    try:
        response = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(
            f"[bridge] ERROR rowid={rowid}: malformed IPC response",
            flush=True,
        )
        return False

    if response.get("status") != "ok":
        print(
            f"[bridge] ERROR rowid={rowid}: "
            f"IPC status={response.get('status')}",
            flush=True,
        )
        return False

    print(
        f"[bridge] STORED generation={generation} "
        f"rowid={rowid} key={pref['key']}",
        flush=True,
    )
    return True


def process_rows(
    last_rowid: int,
    rows: list[dict],
    writer=write_preference,
    generation: int = 0,
) -> tuple[int, bool]:
    """Process rows without acknowledging a failed preference IPC write."""

    for row in rows:
        prefs = extract_preferences(row["text"])

        if not prefs:
            last_rowid = max(last_rowid, row["rowid"])
            continue

        if not all(
            writer(row["rowid"], pref, generation)
            for pref in prefs
        ):
            print(
                f"[bridge] RETRY rowid={row['rowid']} "
                "after IPC recovery",
                flush=True,
            )
            return last_rowid, True

        last_rowid = max(last_rowid, row["rowid"])

    return last_rowid, False


def load_cursor() -> dict | None:
    try:
        raw = CURSOR_PATH.read_text(
            encoding="ascii"
        ).strip()
        obj = json.loads(raw)
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    # RC2 persisted just one integer rowid.
    if type(obj) is int:
        if obj < 0:
            return None
        return {
            "rowid": obj,
            "generation": 0,
            "db_identity": None,
        }

    if not isinstance(obj, dict):
        return None

    rowid = obj.get("rowid")
    generation = obj.get("generation", 0)
    db_identity = obj.get("db_identity")

    if type(rowid) is not int or rowid < 0:
        return None

    if type(generation) is not int or generation < 0:
        return None

    if (
        db_identity is not None
        and not isinstance(db_identity, str)
    ):
        return None

    return {
        "rowid": rowid,
        "generation": generation,
        "db_identity": db_identity,
    }


def save_cursor(
    rowid: int,
    generation: int = 0,
    db_identity: str | None = None,
) -> None:
    CURSOR_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    try:
        os.chmod(CURSOR_PATH.parent, 0o700)
    except OSError:
        pass

    tmp = CURSOR_PATH.with_name(
        CURSOR_PATH.name + ".tmp"
    )

    state = {
        "rowid": int(rowid),
        "generation": int(generation),
        "db_identity": db_identity,
    }

    tmp.write_text(
        json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="ascii",
    )

    os.chmod(tmp, 0o600)
    os.replace(tmp, CURSOR_PATH)


def reconcile_cursor(
    saved: dict | None,
    tail: int,
    db_identity: str,
) -> tuple[dict, str]:
    if saved is None:
        return {
            "rowid": tail,
            "generation": 0,
            "db_identity": db_identity,
        }, "new-tail"

    identity_changed = (
        saved["db_identity"] is not None
        and saved["db_identity"] != db_identity
    )

    if identity_changed or saved["rowid"] > tail:
        return {
            "rowid": tail,
            "generation": saved["generation"] + 1,
            "db_identity": db_identity,
        }, "db-reset-tail"

    return {
        "rowid": saved["rowid"],
        "generation": saved["generation"],
        "db_identity": db_identity,
    }, "resume"


def refresh_cursor_for_db(
    last_rowid: int,
    generation: int,
    db_identity: str,
) -> tuple[int, int, str, str | None]:
    """Detect DB replacement or rowid regression during runtime."""

    tail, current_identity = current_db_snapshot()

    if current_identity != db_identity:
        # A replacement DB may already contain historical rows. Preserve
        # the no-backfill boundary by starting at its current tail.
        return (
            tail,
            generation + 1,
            current_identity,
            "db-replaced",
        )

    if tail < last_rowid:
        # Same database file, but RECORD was cleared/recreated. Rows now
        # present in the reset database belong to the new generation, so
        # begin again at rowid 0 rather than silently losing them.
        return (
            0,
            generation + 1,
            current_identity,
            "rowid-regressed",
        )

    return (
        last_rowid,
        generation,
        current_identity,
        None,
    )


def wait_for_chat_db_state() -> tuple[int, str]:
    """Wait for the Assistant DB at login."""

    announced = False

    while True:
        try:
            return current_db_snapshot()
        except (
            OSError,
            sqlite3.Error,
            ChatDbChanged,
        ):
            if not announced:
                print(
                    f"[bridge] waiting for Chat DB: {DB_PATH}",
                    flush=True,
                )
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
        raise SystemExit(
            f"[bridge] FAIL: IPC client not found: {IPC_CALL}"
        )

    # First install starts at current tail: no historical backfill.
    tail, db_identity = wait_for_chat_db_state()
    saved_cursor = load_cursor()

    cursor, cursor_mode = reconcile_cursor(
        saved_cursor,
        tail,
        db_identity,
    )

    last_rowid = cursor["rowid"]
    generation = cursor["generation"]
    db_identity = cursor["db_identity"]

    save_cursor(
        last_rowid,
        generation,
        db_identity,
    )

    print(
        f"[bridge] starting_after_rowid={last_rowid} "
        f"generation={generation} "
        f"cursor_mode={cursor_mode}",
        flush=True,
    )

    while True:
        try:
            (
                last_rowid,
                generation,
                db_identity,
                reset_reason,
            ) = refresh_cursor_for_db(
                last_rowid,
                generation,
                db_identity,
            )

            if reset_reason is not None:
                save_cursor(
                    last_rowid,
                    generation,
                    db_identity,
                )

                print(
                    f"[bridge] DB_RESET "
                    f"reason={reset_reason} "
                    f"generation={generation} "
                    f"starting_after_rowid={last_rowid}",
                    flush=True,
                )

                time.sleep(POLL_INTERVAL)
                continue

            rows, high_watermark = read_new_user_rows(
                last_rowid,
                expected_identity=db_identity,
            )

            new_last_rowid, retry_required = process_rows(
                last_rowid,
                rows,
                generation=generation,
            )

            if not retry_required:
                new_last_rowid = max(
                    new_last_rowid,
                    high_watermark,
                )

            if new_last_rowid != last_rowid:
                save_cursor(
                    new_last_rowid,
                    generation,
                    db_identity,
                )
                last_rowid = new_last_rowid

            time.sleep(
                1 if retry_required else POLL_INTERVAL
            )

        except KeyboardInterrupt:
            break

        except Exception as exc:
            # Keep watcher alive; never log user message contents.
            print(
                f"[bridge] ERROR "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(1)


if __name__ == "__main__":
    main()
