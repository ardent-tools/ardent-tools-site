# harmonia-serve.tape -- VHS script; generates
# static/casts/harmonia-serve.cast
#
# Shot:         a real server boot -> a health check answering -> a
#               library scan triggered -> its import queue populating,
#               against a small seeded sample-media directory, never any
#               personal library content
#               (crates/archon/src/cli.rs subcommands,
#               crates/paroche/src/routes/{system,library}.rs routes).
# Launch gate:  non-blocking (DESIGN.md §9) -- may launch as an honest
#               placeholder if recording slips.
# Duration:     <=75s cap (DESIGN.md §9); demo-card estimate 1:15.
# Poster frame: the health-check JSON.
# Doesn't show: the two stubbed HTTP-layer resolvers (metadata resolution,
#               curation) -- named directly in the page's solid/open list,
#               not hidden behind this demo.
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

Type "# import queue populating -- metadata resolution and curation stay named as open, not hidden behind this demo"
Enter
Sleep 2s
