# thumos-boot.tape -- planned VHS script; intended output:
# static/casts/thumos-boot.cast (not yet recorded)
#
# Shot:         Full QEMU boot -- MMU/cache init, GIC, scheduler, first
#               timer interrupt, CSPRNG, every subsystem's init step, the
#               banner, boot-to-service handoff, service loop ticking --
#               the exact kernel command sequence CI runs on pushes to
#               main and pull requests targeting main.
# Publish gate: requires the real cast and a reviewed transcript.
# Duration:     planned cap <=90s.
# Poster frame: the banner + first ticks.
# Doesn't show: hardware bring-up on the physical AGM M7 -- still open;
#               the recording claims exactly what CI proves, nothing more.
#
# Run from the thumos repo root:
#        vhs static/tapes/thumos-boot.tape
# Geometry: tuned toward 80x24 to match term-panel.html's
#           data-cols="80" data-rows="24"; confirm the actual PTY size on
#           the build box and retune Width/Height/FontSize if it drifts.
# ANSI palette: applied at playback time by the vendored asciinema-player
#           theme (DESIGN.md §2.2), not by this capture step -- no Theme
#           is set here.

Output static/casts/thumos-boot.cast

Require cargo
Require qemu-system-arm

Set Shell "bash"
Set FontSize 20
Set Width 960
Set Height 580
Set Padding 16
Set TypingSpeed 55ms
Set WaitTimeout 90s
Set CursorBlink false

Hide
Type "clear"
Enter
Show

Type "# thumos -- kernel boot under QEMU, gated on main pushes and pull requests targeting main"
Enter
Sleep 1s

Type "sudo apt-get install -y qemu-system-arm"
Enter
Sleep 1s

# WHY: recorded from a warm target/ (sccache+mold, the fleet's normal build
# cache posture) so the visible build step is an incremental compile, not a
# cold one -- keeps the cast inside the <=90s cap while still typing the
# real CI command verbatim, not an abbreviated stand-in.
Type "cd crates/thumos"
Enter
Type "cargo build --release --target armv7a-none-eabi --features qemu --jobs 8"
Enter
Sleep 8s

Type "THUMOS_QEMU_TIMEOUT=60 ../../scripts/qemu-runner.sh target/armv7a-none-eabi/release/thumos"
Enter

# The boot log is the payoff. Markers below are the real strings CI itself
# greps for (.github/workflows/ci.yml) -- MMU/cache, GIC, scheduler, first
# timer interrupt, CSPRNG, and every subsystem init line stream past first.
Wait+Screen /THUMOS v0\.1\.0/
Sleep 500ms
Wait+Screen /THUMOS-QEMU: boot-complete/
Sleep 500ms
Wait+Screen /THUMOS-QEMU: service-loop ticks=/
Sleep 3s

Type "# service loop ticking -- this is what CI asserts on main pushes and pull requests targeting main"
Enter
Sleep 2s
