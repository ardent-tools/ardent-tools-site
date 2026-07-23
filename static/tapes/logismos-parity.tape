# logismos-parity.tape -- planned VHS script; intended output:
# static/casts/logismos-parity.cast (not yet recorded)
#
# Shot:         the ignored Phase-3 CPU parity test executing exactly once
#               against embeddings_dim1024.safetensors.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=60s.
# Doesn't show: any GPU run. Phase 4 remains hardware-blocked.
#
# Run from the ardent-tools-site root:
#   ARDENT_LOGISMOS_ROOT=/absolute/path/to/logismos vhs static/tapes/logismos-parity.tape
# Prerequisite: Stella model directory at /models/stella-1.5b-v5.

Output static/casts/logismos-parity.cast

Require cargo
Require mktemp

Set Shell "bash"
Set FontSize 20
Set Width 960
Set Height 580
Set Padding 16
Set TypingSpeed 55ms
Set WaitTimeout 60s
Set CursorBlink false

Hide
Type "test -n \"$ARDENT_LOGISMOS_ROOT\" && test -d \"$ARDENT_LOGISMOS_ROOT/.git\""
Enter
Type "cd \"$ARDENT_LOGISMOS_ROOT\""
Enter
Type "LOGISMOS_LOG=\"$(mktemp -t logismos-parity-tape.XXXXXX)\"; trap 'rm -f -- \"$LOGISMOS_LOG\"' EXIT; set -o pipefail"
Enter
Type "test -d /models/stella-1.5b-v5 && test -f phases/03-stella/golden/embeddings_dim1024.safetensors"
Enter
Type "clear"
Enter
Show

Type "# logismos -- ignored CPU parity test; zero tests is not proof"
Enter
Sleep 1s

Type "cargo test -p logismos --test phase_3_stella_parity -- --ignored 2>&1 | tee \"$LOGISMOS_LOG\" && grep -Eq 'test result: ok\\. 1 passed' \"$LOGISMOS_LOG\" && printf 'LOGISMOS_%s\\n' 'PARITY_OK'"
Enter
Wait+Screen /LOGISMOS_PARITY_OK/
Sleep 2s
