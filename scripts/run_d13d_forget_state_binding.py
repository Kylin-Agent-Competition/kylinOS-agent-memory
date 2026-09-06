#!/usr/bin/env python3
"""run_d13d_forget_state_binding.py — D13D Forget state binding generator/verifier CLI。

子命令：
  generate  从 VM 侧 state inventory（真实 DB/state 身份采集结果）生成 binding artifact V1
  verify    静态校验 binding artifact V1（结构/身份/SHA/禁填项）

inventory 由 VM 预置/采集流程产生（真实生产 Repository/API），本 CLI 不连接 DB、
不读取 Gold/expected、不产生正式 raw。契约见 docs/day13/27_…。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory-service"))

from evaluation.d13d_forget_state_binding import (  # noqa: E402
    BINDING_VERSION,
    compute_artifact_sha256,
    verify_artifact_file,
)

DEFAULT_SOURCE_COMMIT = "dc58e83479d718c8e3fbbbbb5d3b3f046f651973"


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit("inventory must be a JSON object")
    return data


def cmd_generate(args: argparse.Namespace) -> int:
    inventory = _load_json(args.inventory)
    payload = {
        "binding_version": BINDING_VERSION,
        "owner": args.owner,
        "approved_by": args.approved_by,
        "approval_reference": args.approval_reference,
        "applicable_source_commit": args.source_commit,
        "environment_id": inventory.get("environment_id"),
        "vm_snapshot": inventory.get("vm_snapshot"),
        "state_root": inventory.get("state_root"),
        "db_identity": inventory.get("db_identity"),
        "retrieval_profile": inventory.get("retrieval_profile"),
        "created_at_utc": inventory.get("created_at_utc"),
        "created_by": args.owner,
        "samples": inventory.get("samples"),
    }
    payload["artifact_sha256"] = compute_artifact_sha256(payload)
    out = Path(args.output)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"generated {out} sha256={payload['artifact_sha256']}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    ok, errors = verify_artifact_file(args.artifact)
    if ok:
        print(f"OK: {args.artifact} 静态校验通过")
        return 0
    print(f"FAIL: {args.artifact}", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="D13D Forget state binding tool")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="从 VM state inventory 生成 binding artifact")
    gen.add_argument("--inventory", required=True, help="VM 侧采集的 state inventory JSON")
    gen.add_argument("--output", required=True, help="输出 artifact 路径")
    gen.add_argument("--owner", default="B（高翌哲）")
    gen.add_argument("--approved-by", default="D/E")
    gen.add_argument(
        "--approval-reference",
        default="D/E 2026-09-06 B-2 ACCEPTED / BLOCKED_PENDING_VM_BINDING_ARTIFACT + B 完整授权",
    )
    gen.add_argument("--source-commit", default=DEFAULT_SOURCE_COMMIT)
    gen.set_defaults(func=cmd_generate)

    ver = sub.add_parser("verify", help="静态校验 binding artifact")
    ver.add_argument("artifact", help="binding artifact JSON 路径")
    ver.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())