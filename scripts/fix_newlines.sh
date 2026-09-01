#!/bin/bash
for f in "$@"; do
    if [ -s "$f" ] && [ "$(xxd -p -l 1 < <(tail -c 1 "$f"))" != "0a" ]; then
        echo "MISSING NEWLINE: $f"
        echo >> "$f"
        echo "  fixed"
    else
        echo "OK: $f"
    fi
done