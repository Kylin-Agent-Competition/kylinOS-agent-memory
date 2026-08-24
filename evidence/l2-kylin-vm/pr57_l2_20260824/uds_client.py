#!/usr/bin/env python3
"""UDS 测试客户端（长度前缀 JSON 协议，FRZ-IPC-001）。

用法：
  python3 uds_client.py --socket PATH --request '<envelope json>'
      → 发送标准 envelope，打印响应 JSON。

  python3 uds_client.py --socket PATH --request '<envelope json>' --frame-hex '0000ffff...'
      → 发送自定义原始帧（帧头+帧体），用于帧错误/超长/非法 UTF-8 测试。

特殊测试模式（L2-B2）：
  --declared-too-large  发送 4 字节帧头声明长度 > 65536
  --invalid-utf8        发送非法 UTF-8 JSON body
"""
import argparse
import json
import socket
import struct
import sys

MAX_MSG_LEN = 65536


def _encode(body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + body


def _send_frame(path: str, frame: bytes) -> str:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect(path)
    s.sendall(frame)
    # 读取响应：先读 4 字节长度，再读 body
    hdr = s.recv(4)
    if len(hdr) < 4:
        s.close()
        return "<no response>"
    (n,) = struct.unpack(">I", hdr)
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            break
        buf += chunk
    s.close()
    return buf.decode("utf-8", errors="replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--socket", required=True)
    ap.add_argument("--request", default=None, help="envelope JSON string")
    ap.add_argument("--frame-hex", default=None, help="raw frame hex (header+body)")
    ap.add_argument("--declared-too-large", action="store_true")
    ap.add_argument("--invalid-utf8", action="store_true")
    args = ap.parse_args()

    if args.declared_too_large:
        # 声明长度 70000（> 65536），body 只有 1 字节 → 服务端应 PROTOCOL_ERROR
        frame = struct.pack(">I", 70000) + b"x"
        print(_send_frame(args.socket, frame))
        return
    if args.invalid_utf8:
        body = b'{"protocol_version":"1.0",\xff\xfe\xfd}'  # 非法 UTF-8
        print(_send_frame(args.socket, _encode(body)))
        return
    if args.frame_hex is not None:
        frame = bytes.fromhex(args.frame_hex)
        print(_send_frame(args.socket, frame))
        return
    if args.request is not None:
        body = args.request.encode("utf-8")
        print(_send_frame(args.socket, _encode(body)))
        return
    ap.error("必须提供 --request / --frame-hex / --declared-too-large / --invalid-utf8")


if __name__ == "__main__":
    main()
