# thumos-boot.tape -- planned VHS script; intended output:
# static/casts/thumos-boot.cast (not yet recorded)
#
# Shot:         the same primary qemu-feature build and runner invocation
#               used by CI, observed at its banner, boot-complete, and
#               service-loop markers. This is not the complete CI sequence.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=90s.
# Doesn't show: physical AGM M7 hardware or the rest of the CI matrix.
#
# Run from the ardent-tools-site root:
#   ARDENT_THUMOS_ROOT=/absolute/path/to/thumos vhs static/tapes/thumos-boot.tape
# Prerequisite: qemu-system-arm is already installed.

Output static/casts/thumos-boot.cast

Require cargo
Require mktemp
Require qemu-system-arm

Set Shell "bash"
Set FontSize 20
Set Width 960
Set Height 580
Set Padding 16
Set TypingSpeed 55ms
Set WaitTimeout 90s
Set CursorBlink false

Hide
Type "test -n \"$ARDENT_THUMOS_ROOT\" && test -d \"$ARDENT_THUMOS_ROOT/.git\""
Enter
Type "cd \"$ARDENT_THUMOS_ROOT/crates/thumos\""
Enter
Type "THUMOS_LOG=\"$(mktemp -t thumos-boot-tape.XXXXXX)\"; trap 'rm -f -- \"$THUMOS_LOG\"' EXIT; set -o pipefail"
Enter
Type "clear"
Enter
Show

Type "# thumos -- primary QEMU build and runner, three headline markers"
Enter
Sleep 1s

Type "cargo build --release --target armv7a-none-eabi --features qemu --jobs 8 && printf 'THUMOS_%s\\n' 'BUILD_OK'"
Enter
Wait+Screen /THUMOS_BUILD_OK/
Sleep 1s

Type "THUMOS_QEMU_TIMEOUT=60 ../../scripts/qemu-runner.sh target/armv7a-none-eabi/release/thumos 2>&1 | tee \"$THUMOS_LOG\" && grep -q 'THUMOS v0.1.0' \"$THUMOS_LOG\" && grep -q 'THUMOS-QEMU: boot-complete' \"$THUMOS_LOG\" && grep -q 'THUMOS-QEMU: service-loop ticks=' \"$THUMOS_LOG\" && printf 'THUMOS_%s\\n' 'BOOT_MARKERS_OK'"
Enter
Wait+Screen /THUMOS_BOOT_MARKERS_OK/
Sleep 3s
