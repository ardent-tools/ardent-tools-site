+++
title = "Ardent Tools"
template = "index.html"

[extra]
kicker = "CODY KICKERTZ · AGENT HARNESS ENGINEERING · REMOTE (AUSTIN, TX)"
h1 = "Systems you can watch working."
lede = "I build agent infrastructure: the standards gates, guardrails, memory, and review loops that let AI agents do real engineering work you can verify. Claims on this site come with recordings or measurement methods attached. The first one is below — a bare-metal OS I wrote, booting."
selected_work = ["aletheia", "kanon", "ergon-tools"]

[extra.hero_demo]
system = "thumos"
action = "kernel boot"
target = "qemu-system-arm -machine virt"
duration = "0:52"
placeholder = "RECORDING FORTHCOMING: full QEMU boot — MMU/cache init, GIC, scheduler, first timer tick, subsystem inits, banner, service loop ticking. The exact commands CI runs on every push."
shows = "The boot banner and the first serviced ticks, once recorded — the exact commands CI already runs on every push."
not_shows = "Hardware bring-up on the physical AGM M7 — still open; the recording will claim exactly what CI proves, no more."
+++

I spent five years in the Marine Corps, then an MBA, then a shift into data and AI engineering — the operations discipline carried over, the domain didn't. Ardent Tools is where I build and publish agent infrastructure: the guardrails, memory systems, and review loops that make AI-driven engineering work checkable rather than trusted on faith. Everything here either runs on screen or states how it was measured. Ardent Tools is the sibling of Ardent Leatherworks, where the same rule holds for belts as for build gates: process is the proof.
