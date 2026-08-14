#!/usr/bin/env bash
set -euo pipefail
# Fail-closed external-link check. A reachable third party's 5xx or a genuine
# request timeout is not link rot, and a deploy must not be hostage to
# another host's transient error. Every other outcome - a rejected 4xx (the
# link is dead), a connection-level failure (DNS/TLS/refused - lychee
# reports none of these with a status code, so they cannot be told apart
# from our own network breaking), or any fault in the checker itself (crash,
# bad config, missing binary, unparseable output) - fails the gate. Retry
# the pass once; classify only lychee's own structured JSON report
# (bin/link_check_contract.py), never its human-readable log.

PROD_OUTPUT=$1
SITE_BASE_URL=$2
CHECK_ROOT=$3

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

BASE_HOST=${SITE_BASE_URL#http://}
BASE_HOST=${BASE_HOST#https://}
BASE_HOST=${BASE_HOST%%/*}
ESCAPED_HOST=${BASE_HOST//./\\.}
RETRY_DELAY=${LINK_CHECK_RETRY_DELAY:-20} # WHY: tests override this to 0.

LYCHEE_LOG="$CHECK_ROOT/lychee.log"
LYCHEE_REPORT="$CHECK_ROOT/lychee.json"
LYCHEE_RECEIPT="$CHECK_ROOT/lychee-degraded-receipt.json"

link_check() {
  lychee --config themes/typikon/ci/lychee.toml \
    --cache=false \
    --root-dir "$PROD_OUTPUT" \
    --exclude "^https?://${ESCAPED_HOST}/" \
    --format json \
    --output "$LYCHEE_REPORT" \
    --no-progress \
    "$PROD_OUTPUT"
}

run_link_check() {
  rm -f "$LYCHEE_REPORT" # WHY: a crash before lychee reaches its output stage leaves no file; a stale one from the prior attempt must never be read as this attempt's result.
  set +e
  link_check >"$LYCHEE_LOG" 2>&1
  LYCHEE_EXIT=$?
  set -e
}

run_link_check
if [[ "$LYCHEE_EXIT" -ne 0 ]]; then
  cat "$LYCHEE_LOG"
  echo "==> external links: first pass failed (lychee exit $LYCHEE_EXIT); retrying once in ${RETRY_DELAY}s"
  sleep "$RETRY_DELAY"
  run_link_check
  if [[ "$LYCHEE_EXIT" -ne 0 ]]; then
    cat "$LYCHEE_LOG"
    if [[ "$LYCHEE_EXIT" -ne 2 ]]; then
      # exit 2 means "checked links, found rejections" - a link-content
      # result. Any other nonzero exit (missing binary, bad config, crash)
      # means lychee itself did not complete a check - a checker fault,
      # never treated as upstream unavailability.
      echo "ERROR: lychee exited $LYCHEE_EXIT (not a link-result exit); treating as a checker fault, not link rot" >&2
      exit 1
    fi
    python3 bin/link_check_contract.py "$LYCHEE_REPORT" --receipt "$LYCHEE_RECEIPT"
  fi
fi
