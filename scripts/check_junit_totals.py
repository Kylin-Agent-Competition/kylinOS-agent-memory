#!/usr/bin/env python3
"""Count testcase outcomes without relying on runner-specific suite attributes."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable


def summarize(paths: Iterable[Path]) -> dict[str, int]:
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for path in paths:
        root = ET.parse(path).getroot()
        for case in root.iter("testcase"):
            totals["tests"] += 1
            if case.find("failure") is not None:
                totals["failures"] += 1
            if case.find("error") is not None:
                totals["errors"] += 1
            if case.find("skipped") is not None:
                totals["skipped"] += 1
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-tests", type=int, required=True)
    parser.add_argument("junit", nargs="+", type=Path)
    args = parser.parse_args(argv)

    totals = summarize(args.junit)
    print(" ".join(f"{key}={value}" for key, value in totals.items()))
    expected = {
        "tests": args.expected_tests,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    return 0 if totals == expected else 1


if __name__ == "__main__":
    sys.exit(main())
