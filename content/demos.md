+++
title = "Demos"
description = "Every recording on one page, click-to-play. Each one is a scripted run of real commands, regenerated when the code changes."
template = "demos.html"

[[extra.demos]]
system = "thumos"
action = "kernel boot"
target = "qemu-system-arm -machine virt"
duration = "0:52"
tape = "/tapes/thumos-boot.tape"
placeholder = "RECORDING FORTHCOMING: full QEMU boot — MMU/cache init, GIC, scheduler, first timer interrupt, CSPRNG, every subsystem's init step, boot-to-service handoff, banner, service loop ticking"
shows = "The exact command sequence CI already runs on every push, ending on the service loop visibly ticking."
not_shows = "Hardware bring-up on the physical AGM M7 — that stays open regardless of what the recording shows."

[[extra.demos]]
system = "kanon"
action = "lint --fix, then gate"
target = "run against the public aletheia repo"
duration = "1:15"
tape = "/tapes/kanon-gate.tape"
placeholder = "RECORDING FORTHCOMING: kanon lint finds a violation (seeded, labeled on-screen as SEEDED VIOLATION — LABELED IN-CAST) → kanon lint --fix clears the mechanical class → kanon gate runs clean"
shows = "The standards engine finding and fixing a real violation class, then passing a clean gate — against a public repo."
not_shows = "kanon's own source. Private by choice, not by necessity."

[[extra.demos]]
system = "aletheia"
action = "memory recall across turns"
target = "local model, no cloud key"
duration = "1:30"
tape = "/tapes/aletheia-memory.tape"
placeholder = "RECORDING FORTHCOMING: TUI session — state a fact in turn 1, ask something unrelated in turn 2, ask for recall in turn 3, agent cites the turn-1 fact back correctly"
shows = "A fact stated in turn 1, recalled correctly and cited back in turn 3, against a local model with no cloud API key."
not_shows = "The desktop app — a v1.0-target preview, not the default onboarding path this recording uses."

[[extra.demos]]
system = "logismos"
action = "CPU golden-fixture parity test"
target = "phase_3_stella_parity, against a committed fixture"
duration = "1:00"
tape = "/tapes/logismos-parity.tape"
placeholder = "RECORDING FORTHCOMING: cargo test -p logismos --test phase_3_stella_parity passing against the committed CPU baseline fixture"
shows = "The correctness harness passing on CPU, against a fixture committed to the repo."
not_shows = "Any GPU run. Phase 4 is hardware-blocked; this recording won't stage one."

[[extra.demos]]
system = "harmonia"
action = "server boot, health check, library scan"
target = "seeded sample media only"
duration = "1:15"
tape = "/tapes/harmonia-serve.tape"
placeholder = "RECORDING FORTHCOMING: harmonia serve boots → a health check answers → a library scan triggers → its import queue populates"
shows = "A real server boot, a health check answering, and a library scan populating an import queue."
not_shows = "The two HTTP-layer resolvers still stubbed for metadata resolution and curation."

[[extra.demos]]
system = "hamma"
action = "handshake + control-protocol type tests"
target = "hamma-core, dictyon"
duration = "0:45"
tape = "/tapes/hamma-tests.tape"
placeholder = "RECORDING FORTHCOMING: cargo test -p hamma-core && cargo test -p dictyon — the Noise-handshake and control-protocol-type tests passing"
shows = "The Noise-handshake and control-protocol-type tests passing — modest, explicitly test-suite-shaped."
not_shows = "Two peers joining a tailnet. That moment doesn't exist yet."

[[extra.demos]]
system = "akroasis"
action = "CHIRP import, then vault verify"
target = "akroasis radio import / vault identity"
duration = "0:50"
placeholder = "RECORDING FORTHCOMING: CHIRP CSV import, validation, Baofeng UV-5R export, then vault identity and tamper-log check — the CLI paths that run today, no radio hardware in frame"
shows = "Real CLI sessions against the shipped crates: syntonia's CHIRP workflow and kryphos's vault, --json output included."
not_shows = "Live mesh traffic or radio programming. The mesh CLI is static until daemon mode lands, and radio read/program waits on the protocol session backend. StubHardware is the default; the caption says so."


+++

Every recording on this page is a scripted run of real commands, regenerated when the code changes. The `.tape` link on each is the script that produced it. Nothing here is staged to look better than what the command actually does.
