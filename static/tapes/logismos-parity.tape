# logismos-parity.tape -- VHS script; generates
# static/casts/logismos-parity.cast
#
# Shot:         the Phase-3 Stella parity test passing against the
#               committed golden fixture
#               (crates/logismos/tests/phase_3_stella_parity.rs against
#               phases/03-stella/golden/cpu_baseline.json) -- the
#               correctness harness built before the GPU was available.
# Launch gate:  non-blocking (DESIGN.md §9) -- may launch as an honest
#               placeholder if recording slips.
# Duration:     <=60s cap (DESIGN.md §9); demo-card estimate 1:00.
# Poster frame: the test summary line.
# Doesn't show: any GPU run. Phase 4 is hardware-blocked; this recording
#               won't stage one to imply otherwise.
#
# Run from the logismos repo root:
#        vhs static/tapes/logismos-parity.tape
# Geometry: tuned toward 80x24 to match term-panel.html's
#           data-cols="80" data-rows="24"; confirm the actual PTY size on
#           the build box and retune Width/Height/FontSize if it drifts.
# ANSI palette: applied at playback time by the vendored asciinema-player
#           theme (DESIGN.md §2.2), not by this capture step -- no Theme
#           is set here.

Output static/casts/logismos-parity.cast

Require cargo

Set Shell "bash"
Set FontSize 20
Set Width 960
Set Height 580
Set Padding 16
Set TypingSpeed 55ms
Set WaitTimeout 60s
Set CursorBlink false

Hide
Type "clear"
Enter
Show

Type "# logismos -- CPU correctness harness, proven before the GPU cutover"
Enter
Sleep 1s

Type "cargo test -p logismos --test phase_3_stella_parity"
Enter
Wait+Screen /test result: ok/
Sleep 2s

Type "# passing against phases/03-stella/golden/cpu_baseline.json -- no GPU run staged; Phase 4 stays hardware-blocked"
Enter
Sleep 2s
