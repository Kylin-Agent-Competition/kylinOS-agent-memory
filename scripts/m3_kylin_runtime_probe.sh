#!/bin/sh
# Frozen M3 host-runtime tool probe.  The runner records this script's exact
# SHA-256, exit status, stdout and stderr before it derives any ToolResult event.
set -eu

sha256sum /etc/os-release
printf 'tool=sha256sum target=/etc/os-release status=success\n'
