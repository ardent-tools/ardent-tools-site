# hamma-tests.tape -- planned VHS script; intended output:
# static/casts/hamma-tests.cast (not yet recorded)
#
# Shot:         the Noise-handshake and control-protocol-type tests
#               passing (`cargo test -p hamma-core`, `cargo test -p
#               dictyon`) -- modest, explicitly test-suite-shaped, matching
#               where the project actually is.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=45s.
# Poster frame: the test summary.
# Doesn't show: two peers joining a tailnet. That moment doesn't exist yet
#               -- the WireGuard data plane isn't wired in; this recording
#               won't stage a fake version of it.
#
# Run from the hamma repo root:
#        vhs static/tapes/hamma-tests.tape
# Geometry: tuned toward 80x24 to match term-panel.html's
#           data-cols="80" data-rows="24"; confirm the actual PTY size on
#           the build box and retune Width/Height/FontSize if it drifts.
# ANSI palette: applied at playback time by the vendored asciinema-player
#           theme (DESIGN.md §2.2), not by this capture step -- no Theme
#           is set here.

Output static/casts/hamma-tests.cast

Require cargo

Set Shell "bash"
Set FontSize 20
Set Width 960
Set Height 580
Set Padding 16
Set TypingSpeed 55ms
Set WaitTimeout 45s
Set CursorBlink false

Hide
Type "clear"
Enter
Show

Type "# hamma -- pre-alpha; modest, explicitly test-suite-shaped"
Enter
Sleep 1s

Type "cargo test -p hamma-core"
Enter
Wait+Screen /test result: ok/
Sleep 1s

Type "cargo test -p dictyon"
Enter
Wait+Screen /test result: ok/
Sleep 1500ms

Type "# Noise handshake + control-protocol types passing -- no tailnet, no staged two-peer join; the WireGuard data plane isn't wired in yet"
Enter
Sleep 2s
