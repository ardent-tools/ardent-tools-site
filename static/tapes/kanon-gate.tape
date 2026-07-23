# kanon-gate.tape -- planned VHS script; intended output:
# static/casts/kanon-gate.cast (not yet recorded)
#
# Shot:         a fresh disposable clone pinned to aletheia
#               1a0ee8a29cb2; lint observes a seeded, labeled, fixable TOML
#               violation, fixes it, proves the file clean, then runs gate.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=75s.
# Doesn't show: Kanon's private source. The seeded defect exists only in the
#               disposable clone and is labeled in the recording.
#
# Run from the ardent-tools-site root:
#   vhs static/tapes/kanon-gate.tape
# Network prerequisite: the public aletheia repository is reachable.

Output static/casts/kanon-gate.cast

Require kanon
Require git
Require mktemp

Set Shell "bash"
Set FontSize 20
Set Width 960
Set Height 580
Set Padding 16
Set TypingSpeed 55ms
Set WaitTimeout 75s
Set CursorBlink false

Hide
Type "clear"
Enter
Type "KANON_TAPE_ROOT=\"$(mktemp -d -t kanon-gate-tape.XXXXXX)\""
Enter
Type "cleanup_kanon_tape() { rm -rf -- \"$KANON_TAPE_ROOT\"; }; trap cleanup_kanon_tape EXIT"
Enter
Type "git clone --quiet https://github.com/forkwright/aletheia.git \"$KANON_TAPE_ROOT/aletheia\""
Enter
Type "ALETHEIA=\"$KANON_TAPE_ROOT/aletheia\""
Enter
Type "PROOF_FILE=\"$ALETHEIA/scripts/release-feature-policy.toml\""
Enter
Type "git -C \"$ALETHEIA\" switch --detach 1a0ee8a29cb2"
Enter
Type "test -z \"$(git -C \"$ALETHEIA\" status --porcelain)\""
Enter
Show

Type "# kanon -- six featured repos carry Kanon config; enforcement is repository-specific"
Enter
Sleep 1s

Type "printf '\nkanon_recording_proof = [\n  \"seed\"\n]\n' >> \"$PROOF_FILE\""
Enter
Type "# SEEDED VIOLATION -- missing TOML trailing comma, absent from aletheia's pinned source"
Enter
Sleep 1s

Type "kanon lint \"$PROOF_FILE\"; rc=$?; test \"$rc\" -eq 1 && printf 'KANON_%s\\n' 'VIOLATION_OK'"
Enter
Wait+Screen /KANON_VIOLATION_OK/
Sleep 1s

Type "kanon lint --fix \"$PROOF_FILE\" && printf 'KANON_%s\\n' 'FIX_OK'"
Enter
Wait+Screen /KANON_FIX_OK/
Sleep 1s

Type "kanon lint \"$PROOF_FILE\" && printf 'KANON_%s\\n' 'LINT_CLEAN_OK'"
Enter
Wait+Screen /KANON_LINT_CLEAN_OK/
Sleep 1s

Type "kanon gate \"$ALETHEIA\" && printf 'KANON_%s\\n' 'GATE_OK'"
Enter
Wait+Screen /KANON_GATE_OK/
Sleep 2s
