#!/usr/bin/env bash

set -euo pipefail

REPO="Kylin-Agent-Competition/kylinOS-agent-memory"

if [[ $# -ne 3 ]]; then
    echo "Usage:"
    echo "  $0 <PR_NUMBER> <HEAD_BRANCH> <REVIEWED_SHA>"
    echo
    echo "Example:"
    echo "  $0 128 feat/d8d-impl-build aba7e48c..."
    exit 2
fi

PR_NUMBER="$1"
BRANCH="$2"
REVIEWED_SHA="$3"

echo "======================================"
echo "Reviewer E — Pre-Merge SHA Gate"
echo "======================================"
echo "Repository   : $REPO"
echo "PR           : #$PR_NUMBER"
echo "Branch       : $BRANCH"
echo "Reviewed SHA : $REVIEWED_SHA"
echo

echo "[1/5] Fetch remote refs"
git fetch origin --prune

REMOTE_SHA="$(git rev-parse "origin/$BRANCH")"

echo "[2/5] Read GitHub PR metadata"
PR_SHA="$(
    gh api "repos/$REPO/pulls/$PR_NUMBER" \
      --jq '.head.sha'
)"

PR_STATE="$(
    gh api "repos/$REPO/pulls/$PR_NUMBER" \
      --jq '.state'
)"

MERGEABLE_STATE="$(
    gh api "repos/$REPO/pulls/$PR_NUMBER" \
      --jq '.mergeable_state'
)"

echo "[3/5] Read GitHub internal pull ref"
PULL_REF_SHA="$(
    gh api "repos/$REPO/git/ref/pull/$PR_NUMBER/head" \
      --jq '.object.sha'
)"

echo
echo "Remote branch : $REMOTE_SHA"
echo "PR head       : $PR_SHA"
echo "Pull ref      : $PULL_REF_SHA"
echo "Reviewed SHA  : $REVIEWED_SHA"
echo "PR state      : $PR_STATE"
echo "Merge state   : $MERGEABLE_STATE"
echo

echo "[4/5] Verify SHA convergence"

FAILED=0

if [[ "$REMOTE_SHA" != "$PR_SHA" ]]; then
    echo "FAIL: remote branch != PR head"
    FAILED=1
fi

if [[ "$REMOTE_SHA" != "$PULL_REF_SHA" ]]; then
    echo "FAIL: remote branch != refs/pull/$PR_NUMBER/head"
    FAILED=1
fi

if [[ "$REMOTE_SHA" != "$REVIEWED_SHA" ]]; then
    echo "FAIL: current branch HEAD != Reviewer E reviewed SHA"
    FAILED=1
fi

if [[ "$PR_STATE" != "open" ]]; then
    echo "FAIL: PR state is not open"
    FAILED=1
fi

if [[ "$FAILED" -ne 0 ]]; then
    echo
    echo "======================================"
    echo "MERGE_GATE_FAILED"
    echo "======================================"
    echo
    echo "DO NOT MERGE."
    echo
    echo "Possible causes:"
    echo "  - GitHub PR synchronize stale"
    echo "  - new commit pushed after review"
    echo "  - wrong local/remote branch"
    echo "  - stale Reviewer SHA"
    exit 1
fi

echo
echo "SHA consistency: PASS"

echo
echo "[5/5] Display current PR checks"
gh pr checks "$PR_NUMBER" \
    --repo "$REPO" || {
        echo
        echo "FAIL: one or more PR checks are not successful."
        exit 1
    }

echo
echo "======================================"
echo "MERGE_GATE_PASS"
echo "======================================"
echo
echo "All authoritative HEADs agree:"
echo
echo "  $REMOTE_SHA"
echo
echo "Reviewer E reviewed the exact current HEAD."
echo "PR checks are successful."

