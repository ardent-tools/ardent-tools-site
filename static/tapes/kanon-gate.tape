# kanon-gate.tape -- planned VHS script; intended output:
# static/casts/kanon-gate.cast (not yet recorded)
#
# Shot:         a fresh disposable clone is pinned to aletheia
#               `1a0ee8a29cb2`; kanon lint finds a seeded, labeled
#               TOML violation, fixes that mechanical class, then runs the
#               non-mutating lint and configured gate.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=75s.
# Poster frame: the violation table.
# Doesn't show: kanon's own source. Private by choice, not by necessity --
#               artifact available on request.
#
# Run from a directory where `kanon` is installed and the network can
#      reach the public aletheia repository:
#        vhs static/tapes/kanon-gate.tape
# Geometry: tuned toward 80x24 to match term-panel.html's
#           data-cols="80" data-rows="24"; confirm the actual PTY size on
#           the build box and retune Width/Height/FontSize if it drifts.
# ANSI palette: applied at playback time by the vendored asciinema-player
#           theme (DESIGN.md §2.2), not by this capture step -- no Theme
#           is set here.

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
# Every mutation belongs to this newly created directory. The EXIT trap is
# installed before the clone and can remove only that mktemp-owned path.
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

# A single mechanical violation staged for this recording only -- a missing
# trailing comma in a TOML array, a real fixable Kanon lint class -- never a
# finding manufactured to look worse or better than reality. The disposable
# clone is removed by the scoped EXIT trap.
Type "printf '\nkanon_recording_proof = [\n  \"seed\"\n]\n' >> \"$PROOF_FILE\""
Enter
Sleep 500ms
Type "# SEEDED VIOLATION -- LABELED IN-CAST (a missing TOML trailing comma staged for this recording; not present on aletheia's actual HEAD)"
Enter
Sleep 1s

Type "kanon lint \"$PROOF_FILE\" || test \"$?\" -eq 1"
Enter
Wait+Screen /missing-trailing-comma|violation/
Sleep 2s

Type "kanon lint --fix \"$PROOF_FILE\""
Enter
Wait+Screen /Applied 1 fix|fixed/
Sleep 1s

Type "kanon lint \"$PROOF_FILE\" && echo '0 violations - lint clean'"
Enter
Wait+Screen /0 violations - lint clean/
Sleep 1s

Type "kanon gate \"$ALETHEIA\""
Enter
Wait+Screen /pass|PASS|gate/
Sleep 2s

Type "# clean gate -- none of kanon's own source appears anywhere in this recording"
Enter
Sleep 2s
