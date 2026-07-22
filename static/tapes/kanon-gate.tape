# kanon-gate.tape -- planned VHS script; intended output:
# static/casts/kanon-gate.cast (not yet recorded)
#
# Shot:         kanon lint finds a violation (seeded, labeled on-screen as
#               SEEDED VIOLATION -- LABELED IN-CAST) -> kanon lint --fix
#               clears the mechanical class -> kanon gate runs clean --
#               run against the public aletheia repo, never kanon's own
#               source (DESIGN.md §4.2 kanon variant).
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=75s.
# Poster frame: the violation table.
# Doesn't show: kanon's own source. Private by choice, not by necessity --
#               artifact available on request.
#
# Run from wherever both kanon and a public aletheia
#      clone are reachable:
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
# ALETHEIA points at a public aletheia clone on the build box -- never
# kanon's own (private) source. Override the env var if the clone lives
# somewhere other than $HOME/dev/aletheia.
Type "ALETHEIA=\"${ALETHEIA:-$HOME/dev/aletheia}\""
Enter
Show

Type "# kanon -- the standards engine gating every public repo on this site, run against aletheia"
Enter
Sleep 1s

# A single mechanical violation staged for this recording only -- a
# freeform (non-structured-tag) comment, a real kanon comment-standard
# lint class -- never a finding manufactured to look worse or better than
# reality, and cleaned up (below) before this tape's git state persists.
Type "echo '// TODO fix this later' >> \"$ALETHEIA/crates/mneme/src/lib.rs\""
Enter
Sleep 500ms
Type "# SEEDED VIOLATION -- LABELED IN-CAST (a freeform-comment violation staged for this recording; not present on aletheia's actual HEAD)"
Enter
Sleep 1s

Type "kanon lint --diff-base main \"$ALETHEIA\""
Enter
Wait+Screen /violation|error|comment-standard/
Sleep 2s

Type "kanon lint --fix \"$ALETHEIA\""
Enter
Wait+Screen /fixed|clean|0 violations/
Sleep 1s

Hide
Type "git -C \"$ALETHEIA\" checkout -- crates/mneme/src/lib.rs"
Enter
Sleep 500ms
Show

Type "kanon gate \"$ALETHEIA\""
Enter
Wait+Screen /pass|PASS|gate/
Sleep 2s

Type "# clean gate -- none of kanon's own source appears anywhere in this recording"
Enter
Sleep 2s
