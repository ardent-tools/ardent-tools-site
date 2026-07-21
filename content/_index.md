+++
title = "Ardent Tools"
template = "index.html"

[extra]
kicker = "CODY KICKERTZ · AI SYSTEMS ARCHITECTURE · REMOTE (AUSTIN, TX)"
h1 = "Systems you can watch working."
lede = "Agent infrastructure: the gates, guardrails, memory, and review loops that make AI-driven engineering verifiable. The first proof is below — a bare-metal OS, booting."
selected_work = ["aletheia", "kanon", "thumos"]
consulting_line = "Ardent Tools takes a small number of consulting engagements: agent infrastructure, governed AI platforms, standards-as-code."

[extra.hero_demo]
system = "thumos"
action = "kernel boot"
target = "qemu-system-arm -machine virt"
duration = "0:52"
placeholder = "RECORDING FORTHCOMING: full QEMU boot — MMU/cache init, GIC, scheduler, first timer tick, subsystem inits, banner, service loop ticking. The exact commands CI runs on every push."
shows = "The boot banner and the first serviced ticks, once recorded — the exact commands CI already runs on every push."
not_shows = "Hardware bring-up on the physical AGM M7 — still open; the recording will claim exactly what CI proves, no more."
+++

Ardent Tools is where I build and publish agent infrastructure: the guardrails, memory systems, and review loops that make AI-driven engineering checkable rather than trusted on faith. Ardent Tools is the sibling of Ardent Leatherworks, a small-batch leather goods maker under the same name.
