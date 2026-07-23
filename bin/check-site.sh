#!/usr/bin/env bash
# Repository-owned, CI-equivalent site gate. By default all build and test
# artifacts live outside the worktree. CI may set ARDENT_RETAIN_VALIDATED_PUBLIC=1
# to move the already validated production artifact to an absent public/ path.
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

for tool in git python3 zola jq rg node npm npx pa11y-ci lychee curl sha256sum cmp; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: required tool is missing: $tool" >&2
    exit 1
  }
done

RETAIN_VALIDATED_PUBLIC=${ARDENT_RETAIN_VALIDATED_PUBLIC:-0}
case "$RETAIN_VALIDATED_PUBLIC" in
  0) ;;
  1)
    [[ ! -e "$ROOT/public" ]] || {
      echo "ERROR: retained-output mode refuses to replace existing public/" >&2
      exit 1
    }
    ;;
  *)
    echo "ERROR: ARDENT_RETAIN_VALIDATED_PUBLIC must be 0 or 1" >&2
    exit 1
    ;;
esac

CHECK_ROOT=$(mktemp -d -t ardent-site-check.XXXXXX)
readonly CHECK_ROOT
PROD_OUTPUT="$CHECK_ROOT/public"
LOCAL_OUTPUT="$CHECK_ROOT/public-local"
SERVER_PID=""
LOCAL_PORT=$((18000 + $$ % 20000))
LOCAL_BASE_URL="http://127.0.0.1:${LOCAL_PORT}"

cleanup() {
  local exit_status=$?
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true # WHY: the server may have exited after a failed gate.
    wait "$SERVER_PID" 2>/dev/null || true # WHY: cleanup must continue when no child remains.
  fi
  # CHECK_ROOT is the readonly path returned by this process's mktemp call.
  rm -rf -- "$CHECK_ROOT" || {
    echo "ERROR: failed to remove gate directory: $CHECK_ROOT" >&2
    return 1
  }
  return "$exit_status"
}
interrupt_gate() {
  exit 130
}
terminate_gate() {
  exit 143
}
trap cleanup EXIT
trap interrupt_gate INT
trap terminate_gate TERM

INITIAL_STATUS=$(git status --porcelain=v1 --untracked-files=all)
PLAYWRIGHT_CONFIG_BEFORE=$(sha256sum playwright.config.ts)

echo "==> frontmatter"
themes/typikon/bin/typikon-validate .

echo "==> zola check"
zola check

echo "==> generated catalog cleanliness"
python3 bin/generate-systems-json.py --output "$CHECK_ROOT/systems.json"
cmp static/systems.json "$CHECK_ROOT/systems.json"

echo "==> production build, CSP, and strict contracts"
zola build --output-dir "$PROD_OUTPUT"
cp _headers "$PROD_OUTPUT/_headers"
cp _redirects "$PROD_OUTPUT/_redirects"
if [[ -f "$PROD_OUTPUT/404/index.html" ]]; then
  cp "$PROD_OUTPUT/404/index.html" "$PROD_OUTPUT/404.html"
fi
themes/typikon/ci/csp-enforce.sh "$PROD_OUTPUT"
python3 bin/validate-site.py "$PROD_OUTPUT"

echo "==> external links"
BASE_URL=$(sed -nE 's/^base_url[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' config.toml | head -1)
BASE_HOST=${BASE_URL#http://}
BASE_HOST=${BASE_HOST#https://}
BASE_HOST=${BASE_HOST%%/*}
ESCAPED_HOST=${BASE_HOST//./\\.}
lychee --config themes/typikon/ci/lychee.toml \
  --cache=false \
  --root-dir "$PROD_OUTPUT" \
  --exclude "^https?://${ESCAPED_HOST}/" \
  "$PROD_OUTPUT"

echo "==> local browser build"
zola build --base-url "$LOCAL_BASE_URL" --output-dir "$LOCAL_OUTPUT"
if [[ -f "$LOCAL_OUTPUT/404/index.html" ]]; then
  cp "$LOCAL_OUTPUT/404/index.html" "$LOCAL_OUTPUT/404.html"
fi
(
  cd "$LOCAL_OUTPUT"
  python3 -m http.server "$LOCAL_PORT" --bind 127.0.0.1
) >"$CHECK_ROOT/server.log" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 40); do
  if curl -fsS "$LOCAL_BASE_URL/" >/dev/null; then
    break
  fi
  sleep 0.25
done
curl -fsS "$LOCAL_BASE_URL/" >/dev/null || {
  cat "$CHECK_ROOT/server.log" >&2
  exit 1
}

echo "==> all-route pa11y"
SITE_OUTPUT_DIR="$LOCAL_OUTPUT" TYPIKON_BASE_URL="$LOCAL_BASE_URL" \
  pa11y-ci --config tests/pa11y.config.cjs

echo "==> all-route Playwright"
export NODE_PATH="$(npm root -g)"
SITE_OUTPUT_DIR="$LOCAL_OUTPUT" TYPIKON_BASE_URL="$LOCAL_BASE_URL" \
PLAYWRIGHT_OUTPUT_DIR="$CHECK_ROOT/playwright-artifacts" \
PLAYWRIGHT_JSON_OUTPUT_FILE="$CHECK_ROOT/playwright.json" \
  npx playwright test

kill "$SERVER_PID" 2>/dev/null || true # WHY: a concurrent server exit is already the desired state.
wait "$SERVER_PID" 2>/dev/null || true # WHY: reap when present; continue when already reaped.
SERVER_PID=""

PLAYWRIGHT_CONFIG_AFTER=$(sha256sum playwright.config.ts)
[[ "$PLAYWRIGHT_CONFIG_BEFORE" == "$PLAYWRIGHT_CONFIG_AFTER" ]] || {
  echo "ERROR: playwright.config.ts changed during the gate" >&2
  exit 1
}
FINAL_STATUS=$(git status --porcelain=v1 --untracked-files=all)
[[ "$INITIAL_STATUS" == "$FINAL_STATUS" ]] || {
  echo "ERROR: gate changed the worktree" >&2
  git status --short >&2
  exit 1
}

if [[ "$RETAIN_VALIDATED_PUBLIC" == 1 ]]; then
  mv -- "$PROD_OUTPUT" "$ROOT/public"
  echo "==> retained the validated production artifact at public/"
fi

echo "PASS: strict site gate; playwright.config.ts preserved; pre-retention worktree state unchanged"
