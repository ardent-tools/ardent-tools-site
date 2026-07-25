#!/usr/bin/env bash
# thumos-boot cast recipe. Reproduces static/casts/thumos-boot.cast: the same
# primary qemu-feature build and runner invocation CI uses, booting the
# bare-metal Rust kernel under qemu-system-arm to its banner, boot-complete,
# and service-loop markers. Not the full CI matrix, not physical AGM M7 hardware.
#
# Reproduce (clones + cross-compiles fresh at the pin; needs qemu-system-arm
# and the armv7a-none-eabi rustup target):   bash thumos-boot.driver.sh
# Record (against a warm pre-built clone - cache warming per CAST-DESIGN A6):
#   ARDENT_THUMOS_ROOT=/path/to/prebuilt/thumos \
#     asciinema rec thumos-boot.cast --overwrite -c 'bash thumos-boot.driver.sh'
# WARNING: no `set -e` - the '&& ok' pattern gates each marker; a failing step
# must drop its marker, not abort the cast mid-run.
export PATH="$HOME/.cargo/bin:$PATH"
export GIT_PAGER=cat
export THUMOS_QEMU_TIMEOUT="${THUMOS_QEMU_TIMEOUT:-60}"

PIN=3352cef887cf
THUMOS="${ARDENT_THUMOS_ROOT:-}"
if [ -z "$THUMOS" ]; then
  THUMOS="$(mktemp -d -t thumos-cast.XXXXXX)/thumos"
  git clone --quiet https://github.com/forkwright/thumos.git "$THUMOS" || exit 1
  git -C "$THUMOS" switch --detach --quiet "$PIN"
  rustup target add armv7a-none-eabi >/dev/null 2>&1
fi

ok() { printf 'THUMOS_%s\n' "$1"; }

cd "$THUMOS/crates/thumos" || exit 1

clear
TS=0.035
prompt() { printf '\033[38;5;245m$\033[0m '; }
typeit() { local c="$1" i; prompt; for ((i=0; i<${#c}; i++)); do printf '%s' "${c:i:1}"; sleep "$TS"; done; printf '\n'; }
run() { typeit "$1"; eval "$1"; }

run '# thumos - bare-metal Rust kernel, no Linux, booting under qemu-system-arm'; sleep 1
run 'cargo build --release --target armv7a-none-eabi --features qemu --jobs 8 && ok BUILD_OK'; sleep 1
# WHY < /dev/null: qemu-runner's -nographic serial console blocks on an
# interactive stdin (e.g. under a recording pty); the boot path takes no input.
run '../../scripts/qemu-runner.sh target/armv7a-none-eabi/release/thumos < /dev/null && ok BOOT_OK'; sleep 2
run '# not shown: physical AGM M7 hardware - qemu proves the boot path, not the modem/wifi/bt/gps blobs'; sleep 3
