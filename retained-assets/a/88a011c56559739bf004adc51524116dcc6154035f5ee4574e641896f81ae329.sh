#!/usr/bin/env bash
# hamma-tests cast recipe. Reproduces static/casts/hamma-tests.cast: run the
# hamma-core and dictyon control-plane test suites against a public clone of
# hamma, watched to their passing markers. Not an end-to-end tailnet.
#
# Reproduce (clones hamma fresh at the pin):   bash hamma-tests.driver.sh
# Record (warm clone, faster - cache warming per CAST-DESIGN A6):
#   ARDENT_HAMMA_ROOT=/path/to/hamma CARGO_TARGET_DIR=/path/to/warm-target \
#     asciinema rec hamma-tests.cast --overwrite -c 'bash hamma-tests.driver.sh'
# WARNING: no `set -e` - the '&& ok' pattern gates each marker; a failing suite
# must drop its marker, not abort the cast mid-run.
export PATH="$HOME/.cargo/bin:$PATH"
export GIT_PAGER=cat

PIN=2423485c5c48
HAMMA="${ARDENT_HAMMA_ROOT:-}"
if [ -z "$HAMMA" ]; then
  HAMMA="$(mktemp -d -t hamma-cast.XXXXXX)/hamma"
  git clone --quiet https://github.com/forkwright/hamma.git "$HAMMA" || exit 1
  git -C "$HAMMA" switch --detach --quiet "$PIN"
fi
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-${HAMMA}-target}"

ok() { printf 'HAMMA_%s\n' "$1"; }

cd "$HAMMA" || exit 1

clear
TS=0.035
prompt() { printf '\033[38;5;245m$\033[0m '; }
typeit() { local c="$1" i; prompt; for ((i=0; i<${#c}; i++)); do printf '%s' "${c:i:1}"; sleep "$TS"; done; printf '\n'; }
run() { typeit "$1"; eval "$1"; }

run '# hamma - current control-plane tests, not an end-to-end tailnet'; sleep 1
run 'git rev-parse --short=12 HEAD'; sleep 1
run 'cargo test -p hamma-core && ok CORE_TESTS_OK'; sleep 2
run 'cargo test -p dictyon && ok DICTYON_TESTS_OK'; sleep 2
run "# not shown: two peers on a tailnet - no wireguard data plane here"; sleep 3
