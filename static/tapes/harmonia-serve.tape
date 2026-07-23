# harmonia-serve.tape -- planned VHS script; intended output:
# static/casts/harmonia-serve.cast (not yet recorded)
#
# Shot:         a real server boot from disposable configuration and SQLite
#               state, followed by the public /api/system/health boundary.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=75s.
# Poster frame: the observed health sentinel.
# Doesn't show: a library scan or import. The current admin-protected scan
#               route returns 202 without performing that work.
#
# Run from the ardent-tools-site root:
#   ARDENT_HARMONIA_ROOT=/absolute/path/to/harmonia vhs static/tapes/harmonia-serve.tape

Output static/casts/harmonia-serve.cast

Require harmonia
Require curl
Require jq
Require mktemp
Require python3

Set Shell "bash"
Set FontSize 20
Set Width 960
Set Height 580
Set Padding 16
Set TypingSpeed 55ms
Set WaitTimeout 75s
Set CursorBlink false

Hide
Type "test -n \"$ARDENT_HARMONIA_ROOT\" && test -d \"$ARDENT_HARMONIA_ROOT/.git\""
Enter
Type "cd \"$ARDENT_HARMONIA_ROOT\""
Enter
Type "HARMONIA_STATE=\"$(mktemp -d -t harmonia-health-tape.XXXXXX)\""
Enter
Type "SERVER_PID=\"\"; cleanup_harmonia_tape() { if test -n \"$SERVER_PID\"; then kill \"$SERVER_PID\" 2>/dev/null || true; wait \"$SERVER_PID\" 2>/dev/null || true; fi; rm -rf -- \"$HARMONIA_STATE\"; }; trap cleanup_harmonia_tape EXIT"
Enter
Type "PORT=\"$(python3 -c 'import socket; s=socket.socket(); s.bind((\"127.0.0.1\",0)); print(s.getsockname()[1]); s.close()')\"; QUIC_PORT=\"$(python3 -c 'import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.bind((\"127.0.0.1\",0)); print(s.getsockname()[1]); s.close()')\""
Enter
Type "mkdir -p \"$HARMONIA_STATE/downloads\" \"$HARMONIA_STATE/podcasts\" \"$HARMONIA_STATE/xdg\""
Enter
Type "printf '[database]\\ndb_path = \"%s/harmonia.db\"\\n\\n[exousia]\\njwt_secret = \"recording-only-secret-at-least-32-bytes\"\\n\\n[paroche]\\nlisten_addr = \"127.0.0.1\"\\nport = %s\\nrenderer_quic_port = %s\\n\\n[ergasia]\\ndownload_dir = \"%s/downloads\"\\nsession_state_path = \"%s/downloads/session\"\\n\\n[komide]\\npodcast_dir = \"%s/podcasts\"\\n' \"$HARMONIA_STATE\" \"$PORT\" \"$QUIC_PORT\" \"$HARMONIA_STATE\" \"$HARMONIA_STATE\" \"$HARMONIA_STATE\" > \"$HARMONIA_STATE/harmonia.toml\""
Enter
Type "export XDG_CONFIG_HOME=\"$HARMONIA_STATE/xdg\" HARMONIA_SECRETS_PATH=\"$HARMONIA_STATE/secrets.toml\""
Enter
Type "clear"
Enter
Show

Type "# harmonia -- disposable boot and public health boundary"
Enter
Sleep 1s

Type "harmonia serve --config \"$HARMONIA_STATE/harmonia.toml\" >\"$HARMONIA_STATE/server.log\" 2>&1 & SERVER_PID=$!"
Enter
Type "READY=; for _ in $(seq 1 160); do kill -0 \"$SERVER_PID\" || { cat \"$HARMONIA_STATE/server.log\"; false; }; if curl -sf --max-time 2 \"http://127.0.0.1:$PORT/api/system/health\" | jq -e '.status == \"ok\"' >/dev/null; then READY=1; break; fi; sleep 0.25; done; test \"$READY\" = 1 && printf 'HARMONIA_%s\\n' 'HEALTH_OK'"
Enter
Wait+Screen /HARMONIA_HEALTH_OK/
Sleep 2s
