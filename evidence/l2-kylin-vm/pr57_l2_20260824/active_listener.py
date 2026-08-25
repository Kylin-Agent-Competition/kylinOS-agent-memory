#!/usr/bin/env python3
"""受控 active socket listener（L2-A1 用）：bind + listen + sleep。
用法：python3 active_listener.py <socket_path>
"""
import socket
import sys
import time

path = sys.argv[1]
s = socket.socket(socket.AF_UNIX)
s.bind(path)
s.listen(8)
print("ACTIVE_LISTENER_READY", flush=True)
time.sleep(300)
