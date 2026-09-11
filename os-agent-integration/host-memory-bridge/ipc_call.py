#!/usr/bin/env python3
"""Small CLI client for the Kylin Memory Service length-prefixed JSON UDS API."""

import json
import os
import socket
import struct
import sys
import uuid

PROTOCOL_VERSION = "1.0"
RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
DEFAULT_SOCKET = f"{RUNTIME_DIR}/kylin-memory/memory.sock"
SOCKET_PATH = os.environ.get("KYLIN_MEMORY_SOCKET", DEFAULT_SOCKET)
TIMEOUT_SECONDS = float(os.environ.get("KYLIN_MEMORY_IPC_TIMEOUT", "10"))


def recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise RuntimeError("socket closed before full response")
        buf += chunk
    return buf


def call(method: str, payload: dict, idempotency_key: str | None = None) -> dict:
    request = {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": "host-" + uuid.uuid4().hex[:12],
        "trace_id": "host-trace-" + uuid.uuid4().hex[:12],
        "method": method,
        "deadline_ms": int(TIMEOUT_SECONDS * 1000),
        "payload": payload,
    }
    if idempotency_key:
        request["idempotency_key"] = idempotency_key

    body = json.dumps(request, ensure_ascii=False).encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(TIMEOUT_SECONDS)
        sock.connect(SOCKET_PATH)
        sock.sendall(struct.pack(">I", len(body)) + body)
        length = struct.unpack(">I", recv_exact(sock, 4))[0]
        return json.loads(recv_exact(sock, length).decode("utf-8"))


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: ipc_call.py METHOD PAYLOAD_JSON [IDEMPOTENCY_KEY]", file=sys.stderr)
        return 2

    method = sys.argv[1]
    try:
        payload = json.loads(sys.argv[2])
    except json.JSONDecodeError as exc:
        print(f"invalid PAYLOAD_JSON: {exc}", file=sys.stderr)
        return 2

    idem = sys.argv[3] if len(sys.argv) >= 4 else None
    response = call(method, payload, idem)
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
