#!/usr/bin/env bash
# kanon-gate cast recipe. Reproduces static/casts/kanon-gate.cast: seed a
# labeled, fixable TOML violation into a pinned public clone of aletheia, lint
# it, fix it, prove it clean, then run the configured gate. kanon's own source
# is never shown - the engine runs against the public clone.
#
# Reproduce (clones aletheia fresh at the pin):   bash kanon-gate.driver.sh
# Record (warm clone, faster - cache warming per CAST-DESIGN A6):
#   ALETHEIA_CLONE=/path/to/warm/aletheia \
#     asciinema rec kanon-gate.cast --overwrite -c 'bash kanon-gate.driver.sh'
# WARNING: no `set -e` - the lint-on-violation beat exits 1 by design (VIOLATION_OK).
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export GIT_PAGER=cat

PIN=05b699215dd4
ALETHEIA_CLONE="${ALETHEIA_CLONE:-}"
if [ -z "$ALETHEIA_CLONE" ]; then
  ALETHEIA_CLONE="$(mktemp -d -t aletheia-cast.XXXXXX)/aletheia"
  git clone --quiet https://github.com/forkwright/aletheia.git "$ALETHEIA_CLONE" || exit 1
fi
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-${ALETHEIA_CLONE}-target}"

ok()   { printf 'KANON_%s\n' "$1"; }
seed() { printf '\nkanon_recording_proof = [\n  "seed"\n]\n' >> "$1"; }

cd "$ALETHEIA_CLONE" || exit 1
git reset --hard --quiet
git clean -fdq
git switch --detach --quiet "$PIN"
PROOF_FILE="scripts/release-feature-policy.toml"

clear
TS=0.035
prompt() { printf '\033[38;5;245m$\033[0m '; }
typeit() { local c="$1" i; prompt; for ((i=0; i<${#c}; i++)); do printf '%s' "${c:i:1}"; sleep "$TS"; done; printf '\n'; }
run() { typeit "$1"; eval "$1"; }

run '# kanon - lint and gate against a pinned public clone of aletheia'; sleep 1
run 'git rev-parse --short=12 HEAD'; sleep 1
run 'git status --porcelain | wc -l'; sleep 2
run '# SEEDED VIOLATION - missing TOML trailing comma - absent from the pinned source'; sleep 1
run 'seed $PROOF_FILE'; sleep 1
run 'kanon lint $PROOF_FILE; rc=$?; test $rc -eq 1 && ok VIOLATION_OK'; sleep 2
run 'kanon lint --fix $PROOF_FILE && ok FIX_OK'; sleep 1
run 'git diff -- $PROOF_FILE'; sleep 2
run 'kanon lint $PROOF_FILE && ok LINT_CLEAN_OK'; sleep 1
run 'kanon gate . && ok GATE_OK'; sleep 2
run "# not shown: kanon's own source - the engine ran against a public clone"; sleep 3

git reset --hard --quiet
