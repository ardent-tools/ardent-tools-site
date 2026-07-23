# hamma-tests.tape -- planned VHS script; intended output:
# static/casts/hamma-tests.cast (not yet recorded)
#
# Shot:         the current hamma-core and dictyon test suites passing.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=45s.
# Doesn't show: two peers joining a tailnet or a WireGuard data plane.
#
# Run from the ardent-tools-site root:
#   ARDENT_HAMMA_ROOT=/absolute/path/to/hamma vhs static/tapes/hamma-tests.tape

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
Type "test -n \"$ARDENT_HAMMA_ROOT\" && test -d \"$ARDENT_HAMMA_ROOT/.git\""
Enter
Type "cd \"$ARDENT_HAMMA_ROOT\""
Enter
Type "clear"
Enter
Show

Type "# hamma -- current control-plane tests, not an end-to-end tailnet"
Enter
Sleep 1s

Type "cargo test -p hamma-core && printf 'HAMMA_%s\\n' 'CORE_TESTS_OK'"
Enter
Wait+Screen /HAMMA_CORE_TESTS_OK/
Sleep 1s

Type "cargo test -p dictyon && printf 'HAMMA_%s\\n' 'DICTYON_TESTS_OK'"
Enter
Wait+Screen /HAMMA_DICTYON_TESTS_OK/
Sleep 2s
