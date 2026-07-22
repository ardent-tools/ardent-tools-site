# harmonia-serve.tape -- planned VHS script; intended output:
# static/casts/harmonia-serve.cast (not yet recorded)
#
# Shot:         a real server boot -> a health check answering -> a
#               library scan triggered -> its import queue populating,
#               against a small seeded sample-media directory, never any
#               personal library content
#               (crates/archon/src/cli.rs subcommands,
#               crates/paroche/src/routes/{system,library}.rs routes).
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=75s.
# Poster frame: the health-check JSON.
# Doesn't show: production behavior beyond the seeded scan, or an
#               end-to-end external-provider flow using real credentials.
#               The live serve path wires metadata and curation adapters.
#
# Run from the harmonia repo root, with a small
#      seeded sample-media directory already in place:
#        vhs static/tapes/harmonia-serve.tape
# Geometry: tuned toward 80x24 to match term-panel.html's
#           data-cols="80" data-rows="24"; confirm the actual PTY size on
#           the build box and retune Width/Height/FontSize if it drifts.
# ANSI palette: applied at playback time by the vendored asciinema-player
#           theme (DESIGN.md §2.2), not by this capture step -- no Theme
#           is set here.

Output static/casts/harmonia-serve.cast

Require harmonia
Require curl

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
# PORT: 8096 matches the fixture default exercised by crates/horismos's
# own tests (handle.rs) -- confirm against the recording box's real
# harmonia.toml before the take and retune if the shipped default differs.
Type "PORT=8096"
Enter
Show

Type "# harmonia -- one server, seeded sample media only, no personal library content"
Enter
Sleep 1s

Type "harmonia db migrate --config harmonia.toml"
Enter
Wait+Screen /migrat|OK|done/
Sleep 1s

Type "harmonia serve --config harmonia.toml &"
Enter
Sleep 3s

Type "curl -s localhost:$PORT/api/system/health"
Enter
Wait+Screen /\{/
Sleep 1500ms

Type "curl -s -X POST localhost:$PORT/api/library/scan"
Enter
Sleep 2s

Type "curl -s localhost:$PORT/api/library/import-queue"
Enter
Wait+Screen /\{|\[/
Sleep 2s

Type "# seeded sample only -- no external-provider credentials or provider end-to-end flow in this shot"
Enter
Sleep 2s
