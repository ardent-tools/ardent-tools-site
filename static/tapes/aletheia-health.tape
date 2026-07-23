# aletheia-health.tape -- planned VHS script; intended output:
# static/casts/aletheia-health.cast (not yet recorded)
#
# Shot:         a disposable copy of the repository's demo instance passes
#               config validation, boots, answers its public health route,
#               and exposes the seeded demo agent.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=60s.
# Poster frame: the observed health and agent-registration sentinels.
# Doesn't show: memory recall, an LLM response, the TUI, or the desktop app.
#               No model is pulled or contacted by this boot/health plan.
#
# Run from the ardent-tools-site root:
#   ARDENT_ALETHEIA_ROOT=/absolute/path/to/aletheia vhs static/tapes/aletheia-health.tape

Output static/casts/aletheia-health.cast

Require aletheia
Require curl
Require jq
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
Type "test -n \"$ARDENT_ALETHEIA_ROOT\" && test -d \"$ARDENT_ALETHEIA_ROOT/.git\""
Enter
Type "cd \"$ARDENT_ALETHEIA_ROOT\""
Enter
Type "ALETHEIA_STATE=\"$(mktemp -d -t aletheia-health-tape.XXXXXX)\""
Enter
Type "SERVER_PID=\"\"; cleanup_aletheia_tape() { if test -n \"$SERVER_PID\"; then kill \"$SERVER_PID\" 2>/dev/null || true; wait \"$SERVER_PID\" 2>/dev/null || true; fi; rm -rf -- \"$ALETHEIA_STATE\"; }; trap cleanup_aletheia_tape EXIT"
Enter
Type "mkdir -p \"$ALETHEIA_STATE/instance\" && cp -a demo/instance/. \"$ALETHEIA_STATE/instance/\""
Enter
Type "clear"
Enter
Show

Type "# aletheia -- disposable demo boot and public health, no recall claim"
Enter
Sleep 1s

Type "aletheia -r \"$ALETHEIA_STATE/instance\" check-config && printf 'ALETHEIA_%s\\n' 'CONFIG_OK'"
Enter
Wait+Screen /ALETHEIA_CONFIG_OK/
Sleep 1s

Type "aletheia -r \"$ALETHEIA_STATE/instance\" serve >\"$ALETHEIA_STATE/server.log\" 2>&1 & SERVER_PID=$!"
Enter
Type "READY=; for _ in $(seq 1 120); do kill -0 \"$SERVER_PID\" || { cat \"$ALETHEIA_STATE/server.log\"; false; }; if curl -sf --max-time 2 http://127.0.0.1:18799/api/health | jq -e '.status == \"healthy\" or .status == \"degraded\"' >/dev/null; then READY=1; break; fi; sleep 0.25; done; test \"$READY\" = 1 && printf 'ALETHEIA_%s\\n' 'HEALTH_OK'"
Enter
Wait+Screen /ALETHEIA_HEALTH_OK/
Sleep 1s

Type "curl -sf --max-time 2 -H 'X-Requested-With: aletheia' http://127.0.0.1:18799/api/v1/nous | jq -e '[(.items // .)[] | select(.id == \"demo\")] | length >= 1' >/dev/null && printf 'ALETHEIA_%s\\n' 'DEMO_AGENT_OK'"
Enter
Wait+Screen /ALETHEIA_DEMO_AGENT_OK/
Sleep 2s
