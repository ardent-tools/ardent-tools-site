#!/usr/bin/env bash
set -euo pipefail
# hamma-tests cast recipe. Reproduces static/casts/hamma-tests.cast: run the
# hamma-core and dictyon control-plane test suites against a public clone of
# hamma, watched to their passing markers. Not an end-to-end tailnet.
#
# Reproduce (clones hamma fresh at the pin):   bash hamma-tests.driver.sh
# Record (warm clone, faster - cache warming per CAST-DESIGN A6):
#   ARDENT_HAMMA_ROOT=/path/to/hamma \
#     asciinema rec hamma-tests.cast --overwrite -c 'bash hamma-tests.driver.sh'
# Strict mode protects setup. run() locally permits a failing shown command so
# its missing marker documents the failure instead of aborting the cast mid-run.
export PATH="$HOME/.cargo/bin:$PATH"
export GIT_PAGER=cat

PIN=2423485c5c48
HAMMA="${ARDENT_HAMMA_ROOT:-}"
if [[ -z "$HAMMA" ]]; then
  HAMMA="$(mktemp -d -t hamma-cast.XXXXXX)/hamma"
  git clone --quiet https://github.com/forkwright/hamma.git "$HAMMA" || exit 1
  git -C "$HAMMA" switch --detach --quiet "$PIN"
fi

ok() { printf 'HAMMA_%s\n' "$1"; }

cd "$HAMMA" || exit 1

clear
TS=0.035
prompt() { printf '\033[38;5;245m$\033[0m '; }
typeit() { local c="$1" i; prompt; for ((i=0; i<${#c}; i++)); do printf '%s' "${c:i:1}"; sleep "$TS"; done; printf '\n'; }
run() { typeit "$1"; set +e; eval "$1"; set -e; }

run '# hamma - current control-plane tests, not an end-to-end tailnet'; sleep 1
run 'git rev-parse --short=12 HEAD'; sleep 1
run 'env -u CARGO_TARGET_DIR cargo test -p hamma-core && ok CORE_TESTS_OK'; sleep 2
run 'env -u CARGO_TARGET_DIR cargo test -p dictyon && ok DICTYON_TESTS_OK'; sleep 2
run "# not shown: two peers on a tailnet - no wireguard data plane here"; sleep 3
