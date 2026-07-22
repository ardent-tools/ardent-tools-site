# aletheia-memory.tape -- planned VHS script; intended output:
# static/casts/aletheia-memory.cast (not yet recorded)
#
# Shot:         TUI session -- state a fact in turn 1, ask something
#               unrelated in turn 2, ask for recall in turn 3, the agent
#               cites the turn-1 fact back correctly. Local model
#               (llama3.2 via ollama), no cloud API key
#               (aletheia/demo/README.md).
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=90s.
# Poster frame: the recall answer.
# Doesn't show: the desktop app -- a v1.0-target preview, installed
#               separately from source, not the default onboarding path
#               this recording uses.
#
# Run from the aletheia repo root:
#        vhs static/tapes/aletheia-memory.tape
# Geometry: tuned toward 80x24 to match term-panel.html's
#           data-cols="80" data-rows="24"; confirm the actual PTY size on
#           the build box and retune Width/Height/FontSize if it drifts.
# ANSI palette: applied at playback time by the vendored asciinema-player
#           theme (DESIGN.md §2.2), not by this capture step -- no Theme
#           is set here.

Output static/casts/aletheia-memory.cast

Require ollama
Require aletheia

Set Shell "bash"
Set FontSize 20
Set Width 960
Set Height 580
Set Padding 16
Set TypingSpeed 55ms
Set WaitTimeout 90s
Set CursorBlink false

# Setup is one-time and stays off-camera: ollama already serving llama3.2,
# and demo/instance/config/aletheia.toml already pointed at it (per
# demo/README.md's "Update the model name" step, done before this tape
# runs). The visible cast starts at `aletheia -r demo/instance tui` so the
# ~90s budget goes to the recall proof itself, not model-pull time.
Hide
Type "ollama serve &"
Enter
Sleep 2s
Type "ollama pull llama3.2"
Enter
Sleep 2s
Type "aletheia -r demo/instance serve &"
Enter
Sleep 2s
Type "clear"
Enter
Show

Type "# aletheia -- local model (llama3.2 via ollama), no cloud API key, demo port 18799"
Enter
Sleep 1s

Type "aletheia -r demo/instance tui"
Enter
Sleep 3s

# WHY: the exact in-TUI keystrokes (submit key, any slash-commands) are
# unverified here -- confirm against a real `aletheia -r demo/instance tui`
# session and `aletheia --help` / docs/QUICKSTART.md on the build box
# before recording. Never invent a flag or keybinding not present in
# --help output (DESIGN.md §9, aletheia-memory row).
Type "My favorite deploy target is gfx1100."
Enter
Sleep 4s

Type "What's a reasonable Tuesday lunch in Austin?"
Enter
Sleep 4s

Type "What did I say my favorite deploy target was?"
Enter
Sleep 5s

Type "# turn 3 -- the agent cites the turn-1 fact back; this is the whole demo"
Enter
Sleep 2s
