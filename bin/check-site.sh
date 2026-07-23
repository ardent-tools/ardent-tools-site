#!/usr/bin/env bash
# Repository-owned, CI-equivalent site gate. By default all build and test
# artifacts live outside the worktree. CI may set ARDENT_RETAIN_VALIDATED_PUBLIC=1
# to move the already validated production artifact to an absent public/ path.
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"

BUILD_REVISION=${ARDENT_BUILD_REVISION:-$(git rev-parse --verify 'HEAD^{commit}')}
if [[ ! "$BUILD_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: ARDENT_BUILD_REVISION must be exactly one lowercase 40-hex commit" >&2
  exit 1
fi
RESOLVED_REVISION=$(git rev-parse --verify "${BUILD_REVISION}^{commit}" 2>/dev/null) || {
  echo "ERROR: build revision does not resolve to a commit in this checkout: $BUILD_REVISION" >&2
  exit 1
}
[[ "$RESOLVED_REVISION" == "$BUILD_REVISION" ]] || {
  echo "ERROR: build revision is ambiguous or does not resolve exactly: $BUILD_REVISION" >&2
  exit 1
}
readonly BUILD_REVISION

for tool in git python3 zola node npm npx pa11y-ci lychee curl sha256sum cmp typst pdftotext pdffonts; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: required tool is missing: $tool" >&2
    exit 1
  }
done
ASSET_EPOCH=$(python3 -c 'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("config.toml").read_text())["extra"]["asset_epoch"])')
[[ "$ASSET_EPOCH" =~ ^[1-9][0-9]*$ ]] || {
  echo "ERROR: config.toml extra.asset_epoch must be a nonzero decimal string" >&2
  exit 1
}
readonly ASSET_EPOCH
SITE_BASE_URL=$(python3 -c 'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("config.toml").read_text())["base_url"])')
[[ "$SITE_BASE_URL" =~ ^https://[^/]+$ ]] || {
  echo "ERROR: config.toml base_url must be one canonical HTTPS origin without a trailing slash" >&2
  exit 1
}
readonly SITE_BASE_URL
[[ "$(typst --version)" == typst\ 0.14.2* ]] || {
  echo "ERROR: Typst 0.14.2 is required for the tracked résumé" >&2
  exit 1
}

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

echo "==> integrity regression tests"
python3 -m unittest discover -s tests -p 'test_*.py'

echo "==> resume reproducibility and factual manifest"
python3 bin/validate-resume-fonts.py --font-dir resume/fonts
typst compile --root "$ROOT" --font-path resume/fonts --ignore-system-fonts \
  --ignore-embedded-fonts resume/cody-kickertz-resume.typ "$CHECK_ROOT/cody-kickertz-resume-a.pdf"
typst compile --root "$ROOT" --font-path resume/fonts --ignore-system-fonts \
  --ignore-embedded-fonts resume/cody-kickertz-resume.typ "$CHECK_ROOT/cody-kickertz-resume-b.pdf"
cmp "$CHECK_ROOT/cody-kickertz-resume-a.pdf" "$CHECK_ROOT/cody-kickertz-resume-b.pdf"
cmp static/files/cody-kickertz-resume.pdf "$CHECK_ROOT/cody-kickertz-resume-a.pdf"
pdffonts "$CHECK_ROOT/cody-kickertz-resume-a.pdf" > "$CHECK_ROOT/cody-kickertz-resume-fonts.txt"
python3 bin/validate-resume-fonts.py --font-dir resume/fonts \
  --pdffonts "$CHECK_ROOT/cody-kickertz-resume-fonts.txt"
pdftotext "$CHECK_ROOT/cody-kickertz-resume-a.pdf" "$CHECK_ROOT/cody-kickertz-resume.txt"
python3 bin/validate-resume.py "$CHECK_ROOT/cody-kickertz-resume.txt"

echo "==> production build, CSP, and strict contracts"
zola build --output-dir "$PROD_OUTPUT"
cp _headers "$PROD_OUTPUT/_headers"
cp _redirects "$PROD_OUTPUT/_redirects"
# Zola copies three theme directory placeholders. They are repository
# scaffolding, not deployable public artifacts; remove only these exact paths
# before the retained-tree manifest defines the production artifact set.
for placeholder in \
  "$PROD_OUTPUT/casts/.gitkeep" \
  "$PROD_OUTPUT/css/.gitkeep" \
  "$PROD_OUTPUT/js/.gitkeep"; do
  if [[ -f "$placeholder" && ! -L "$placeholder" ]]; then
    rm -- "$placeholder"
  fi
done
printf '%s\n' "$BUILD_REVISION" > "$PROD_OUTPUT/build-revision.txt"
if [[ -f "$PROD_OUTPUT/404/index.html" ]]; then
  cp "$PROD_OUTPUT/404/index.html" "$PROD_OUTPUT/404.html"
fi
python3 bin/html_authority.py "$PROD_OUTPUT" \
  --revision "$BUILD_REVISION" --base-url "$SITE_BASE_URL"
python3 bin/release_manifest.py "$PROD_OUTPUT" \
  --revision "$BUILD_REVISION" --asset-epoch "$ASSET_EPOCH"
themes/typikon/ci/csp-enforce.sh "$PROD_OUTPUT"
python3 bin/validate-site.py "$PROD_OUTPUT" --expected-revision "$BUILD_REVISION"

echo "==> external links"
BASE_URL="$SITE_BASE_URL"
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
