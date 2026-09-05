#!/usr/bin/env bash
# D14D G0/G2 release preflight. It never installs, restarts, or deletes.
set -euo pipefail

TESTED_COMMIT=""
PACKAGE_DIR=""
PACKAGE_TAR=""
D13D_FREEZE=""
EVIDENCE_DIR=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/collect_d14d_preflight.sh \
    --tested-commit <40-hex-sha> \
    --package-dir <package-root> \
    --package-tar <release-tarball> \
    --d13d-freeze <environment_freeze.json> \
    --evidence-dir <repo>/evidence/l3-kylin-vm/d14d_<UTC_RUN_ID>

The command only verifies release inputs and writes PREPARED or BLOCKED evidence.
It does not install a package, operate systemd, modify VM state, or remove files.
EOF
}

die_usage() {
  echo "[d14d-preflight] ERROR: $*" >&2
  usage >&2
  exit 2
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --tested-commit) TESTED_COMMIT="${2:-}"; shift 2 ;;
    --package-dir) PACKAGE_DIR="${2:-}"; shift 2 ;;
    --package-tar) PACKAGE_TAR="${2:-}"; shift 2 ;;
    --d13d-freeze) D13D_FREEZE="${2:-}"; shift 2 ;;
    --evidence-dir) EVIDENCE_DIR="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) die_usage "unknown argument: $1" ;;
  esac
done

[ "$(uname -s)" = "Linux" ] || die_usage "D14D preflight must run on the target Linux VM"
[ -n "$TESTED_COMMIT" ] || die_usage "--tested-commit is required"
[ -n "$PACKAGE_DIR" ] || die_usage "--package-dir is required"
[ -n "$PACKAGE_TAR" ] || die_usage "--package-tar is required"
[ -n "$D13D_FREEZE" ] || die_usage "--d13d-freeze is required"
[ -n "$EVIDENCE_DIR" ] || die_usage "--evidence-dir is required"
[[ "$TESTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die_usage "--tested-commit must be a 40-character lowercase SHA"

REPO_DIR="$(git rev-parse --show-toplevel 2>/dev/null)" || die_usage "run from a Git worktree"
EXPECTED_ROOT="$REPO_DIR/evidence/l3-kylin-vm"
case "$EVIDENCE_DIR" in
  "$EXPECTED_ROOT"/d14d_*) ;;
  *) die_usage "--evidence-dir must be under $EXPECTED_ROOT/d14d_<UTC_RUN_ID>" ;;
esac

if [ -e "$EVIDENCE_DIR" ]; then
  die_usage "evidence directory already exists: $EVIDENCE_DIR"
fi

PACKAGE_DIR="$(readlink -f "$PACKAGE_DIR")"
PACKAGE_TAR="$(readlink -f "$PACKAGE_TAR")"
D13D_FREEZE="$(readlink -f "$D13D_FREEZE")"
[ -d "$PACKAGE_DIR" ] || die_usage "package directory does not exist"
[ -f "$PACKAGE_TAR" ] || die_usage "package tarball does not exist"
[ -f "$D13D_FREEZE" ] || die_usage "D13D freeze record does not exist"

mkdir -p "$EVIDENCE_DIR"
COMMANDS_LOG="$EVIDENCE_DIR/commands.log"
IDENTITY_JSON="$EVIDENCE_DIR/release_identity.json"

log() {
  printf '%s\n' "$*" | tee -a "$COMMANDS_LOG"
}

blockers=()
add_blocker() {
  blockers+=("$1")
  log "BLOCKED: $1"
}

log "d14d_preflight_started_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "tested_commit=$TESTED_COMMIT"
log "package_dir=$PACKAGE_DIR"
log "package_tar=$PACKAGE_TAR"
log "d13d_freeze=$D13D_FREEZE"

actual_head="$(git rev-parse HEAD)"
if [ "$actual_head" != "$TESTED_COMMIT" ]; then
  add_blocker "VM worktree HEAD does not match tested_commit (head=$actual_head)"
fi
if [ -n "$(git status --porcelain)" ]; then
  add_blocker "VM worktree is not clean"
fi

for required_file in manifest.json SHA256SUMS VERSION; do
  if [ ! -f "$PACKAGE_DIR/$required_file" ]; then
    add_blocker "package is missing $required_file"
  fi
done

package_manifest_sha256=""
package_tar_sha256="$(sha256sum "$PACKAGE_TAR" | awk '{print $1}')"
if [ -f "$PACKAGE_DIR/manifest.json" ] && [ -f "$PACKAGE_DIR/SHA256SUMS" ]; then
  package_manifest_sha256="$(sha256sum "$PACKAGE_DIR/manifest.json" | awk '{print $1}')"
  if ! (cd "$PACKAGE_DIR" && sha256sum -c SHA256SUMS) >>"$COMMANDS_LOG" 2>&1; then
    add_blocker "package SHA256SUMS verification failed"
  fi

  manifest_commit="$(python3 - "$PACKAGE_DIR/manifest.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as source:
    value = json.load(source).get("source_commit", "")
print(value)
PY
)"
  if [ "$manifest_commit" != "$TESTED_COMMIT" ]; then
    add_blocker "package manifest source_commit does not match tested_commit (manifest=$manifest_commit)"
  fi
fi

freeze_result="$(python3 - "$D13D_FREEZE" "$TESTED_COMMIT" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as source:
    record = json.load(source)
problems = []
if record.get("freeze_status") != "FROZEN":
    problems.append("D13D freeze_status is not FROZEN")
if record.get("tested_commit") != sys.argv[2]:
    problems.append("D13D tested_commit does not match D14D tested_commit")
print("\n".join(problems))
PY
)"
if [ -n "$freeze_result" ]; then
  while IFS= read -r problem; do
    [ -n "$problem" ] && add_blocker "$problem"
  done <<< "$freeze_result"
fi

if [ "${#blockers[@]}" -eq 0 ]; then
  release_status="PREPARED"
  log "G0/G2 preflight passed; install and VM lifecycle gates remain unexecuted"
else
  release_status="BLOCKED"
fi

worktree_clean="true"
if [ -n "$(git status --porcelain)" ]; then
  worktree_clean="false"
fi

python3 - "$IDENTITY_JSON" "$release_status" "$TESTED_COMMIT" "$actual_head" "$worktree_clean" \
  "$PACKAGE_DIR" "$package_manifest_sha256" "$package_tar_sha256" "$D13D_FREEZE" \
  "${blockers[@]}" <<'PY'
import json, sys

target, status, tested, head, worktree_clean, package_dir, manifest_sha, package_tar_sha, freeze = sys.argv[1:10]
blockers = sys.argv[10:]
record = {
    "schema_version": "d14d-release-preflight/v1",
    "release_status": status,
    "tested_commit": tested,
    "worktree_head": head,
    "worktree_clean": worktree_clean == "true",
    "package_dir": package_dir,
    "package_manifest_sha256": manifest_sha or None,
    "package_tar_sha256": package_tar_sha or None,
    "d13d_freeze_reference": freeze,
    "completed_gates": ["G0", "G2"] if status == "PREPARED" else [],
    "blockers": blockers,
    "limitations": "No package installation, systemd operation, SDK call, reboot, upgrade, uninstall, or rollback was performed.",
}
with open(target, "w", encoding="utf-8") as output:
    json.dump(record, output, indent=2, sort_keys=True)
    output.write("\n")
PY

sha256sum "$COMMANDS_LOG" "$IDENTITY_JSON" > "$EVIDENCE_DIR/SHA256SUMS"
log "release_status=$release_status"
log "evidence_dir=$EVIDENCE_DIR"

if [ "$release_status" = "BLOCKED" ]; then
  exit 1
fi
