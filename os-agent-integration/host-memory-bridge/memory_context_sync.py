#!/usr/bin/env python3
"""Export active/current memory preferences into a tiny runtime context sidecar."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
IPC = Path(os.environ.get("KYLIN_MEMORY_IPC_CLIENT", str(HERE / "ipc_call.py"))).expanduser()
USER_ID = os.environ.get("KYLIN_MEMORY_USER_ID", "local-user")
POLL = float(os.environ.get("KYLIN_MEMORY_CONTEXT_POLL", "0.5"))
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
ALLOWED_LANGUAGES = {"Python", "C++", "Java", "Rust", "Go"}
OUT = Path(
    os.environ.get(
        "KYLIN_MEMORY_ACTIVE_CONTEXT",
        str(RUNTIME_DIR / "kylin-memory" / "active-context.txt"),
    )
).expanduser()


def atomic_write(text: str) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(OUT.parent, 0o700)
    except OSError:
        pass
    tmp = OUT.with_name(OUT.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, OUT)


def fetch_language() -> str | None:
    proc = subprocess.run(
        [
            sys.executable,
            str(IPC),
            "preference.list",
            json.dumps({"user_id": USER_ID}, ensure_ascii=False),
        ],
        text=True,
        capture_output=True,
        timeout=3,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ipc_exit_{proc.returncode}")
    response = json.loads(proc.stdout)
    if response.get("status") != "ok":
        raise RuntimeError(f"ipc_status_{response.get('status')}")

    items = (response.get("data") or {}).get("items") or []
    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        current = item.get("current")
        if not isinstance(current, dict):
            continue
        value = current.get("preference_value")
        if (
            current.get("preference_key") == "project_language"
            and current.get("memory_status") == "active"
            and current.get("is_current") is True
            and isinstance(value, str)
            and value.strip() in ALLOWED_LANGUAGES
        ):
            candidates.append(current)

    if not candidates:
        return None
    candidates.sort(key=lambda row: int(row.get("version", 0)))
    return candidates[-1]["preference_value"].strip()


def render(language: str | None) -> str:
    if not language:
        return ""
    return (
        "[Internal Memory Context]\n"
        f"Active saved preference: preferred project programming language = {language}.\n"
        "Apply this only when the current request makes programming-language choice relevant "
        "and does not explicitly specify another language.\n"
        "The current user request has higher priority than this saved preference.\n"
        "Do not mention this internal memory context unless directly relevant.\n"
        "[/Internal Memory Context]\n\n"
    )


def main() -> None:
    last = None
    print(f"[context-sync] ipc={IPC}", flush=True)
    print(f"[context-sync] out={OUT}", flush=True)
    while True:
        try:
            language = fetch_language()
            text = render(language)
            if text != last:
                atomic_write(text)
                # Do not log preference values: journald is operational evidence,
                # not a second persistence channel for user memory content.
                print(
                    f"[context-sync] updated active={'yes' if language else 'no'}",
                    flush=True,
                )
                last = text
        except KeyboardInterrupt:
            break
        except Exception as exc:
            # Fail closed for memory use: stale context must never survive a
            # Memory Service/IPC failure.
            if last != "":
                atomic_write("")
                last = ""
            print(
                f"[context-sync] unavailable -> context cleared ({type(exc).__name__})",
                flush=True,
            )
        time.sleep(POLL)


if __name__ == "__main__":
    main()
