+++
title = "thumos"
description = "A bare-metal Rust phone OS for the AGM M7 — no Linux underneath. The kernel boots end-to-end under QEMU, and CI proves it on every push."
weight = 1
template = "system.html"

[extra]
badge = "BOOTS UNDER EMULATION"
repo = "https://github.com/forkwright/thumos"
stack = "Rust · bare-metal armv7a · QEMU CI"
demo_len = "0:52"

[extra.headline_claim]
claim = "Kernel boots end-to-end under QEMU"
receipt = "CI runs this boot on every push and asserts the service loop ticks · .github/workflows/ci.yml"

[extra.demo]
system = "thumos"
action = "kernel boot"
target = "qemu-system-arm -machine virt"
duration = "0:52"
tape = "/tapes/thumos-boot.tape"
placeholder = "RECORDING FORTHCOMING: full QEMU boot — MMU/cache init, GIC, scheduler, first timer interrupt, CSPRNG, every subsystem's init step, boot-to-service handoff, banner, service loop ticking"
shows = "The exact command sequence CI already runs on every push, ending on the service loop visibly ticking."
not_shows = "Hardware bring-up on the physical AGM M7 — that stays open regardless of what the recording shows; QEMU proves the boot path, not the modem/WiFi/BT/GPS vendor blobs."
+++

## What it is

thumos is a phone operating system written from the kernel up in Rust, targeting a $90 dumbphone (the AGM M7 — MediaTek MT6739, 1 GB RAM, 240x320 screen). There is no Linux underneath it — kernel, memory manager, scheduler, and userspace crates are all Rust, cross-compiled to bare metal. The feature set targets secure communication and counter-surveillance: on-device detection for IMSI-catcher-shaped cell towers, MAC/IMEI randomization at the register level, encrypted storage, and a cellular modem firewalled at the driver boundary rather than trusted directly.

The one thing the modem, WiFi, Bluetooth, and GPS radios have in common is that MediaTek ships them as binary-only vendor blobs — there's no way to replace them with Rust, so thumos treats them as an untrusted peripheral behind a driver boundary instead of pretending they don't exist.

## Decisions and trade-offs

### Prove the boot path in emulation before the hardware exists

Rather than wait for reliable access to physical AGM M7 hardware to validate anything, the kernel boots under QEMU (`qemu-system-arm -machine virt`) and CI asserts that boot on every push. This was a deliberate call: an emulated boot that runs on every commit is worth more than an occasional manual test against real hardware, even though QEMU can't exercise the MT6739's actual radio silicon. The rejected alternative — waiting for stable hardware access before standing up any CI signal — would have meant months with no automated proof the kernel even starts.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Kernel language and target | Bare-metal Rust, kernel excluded from the main workspace for a clean `armv7a-none-eabi` cross-compile | Leaning on Linux's existing driver ecosystem | Every subsystem written and tested from scratch, no free drivers |
| Capability labeling | A capability counts as supported only once a boot or userspace call path reaches it | Calling a crate "supported" the moment it compiles | Several implemented capabilities (UI routing, Bluetooth/GPS control, BT audio, mesh/inbox) sit unreachable, named as such |

## What's solid / what's open

**Solid:** the kernel boots end-to-end under QEMU — MMU/cache setup, the GIC, the scheduler, the first timer interrupt, the CSPRNG, every subsystem's init step, the boot-to-service handoff, and a cooperative service loop running as PID 0 off a 100 Hz timer. CI gates every push on the kernel's host test suite, the bare-metal cross-compile, and the boot itself. The kernel implements and unit-tests an OS core: memory management, interrupts and scheduling, IPC and signals, syscalls, a VFS, a CSPRNG, capabilities, power management, a watchdog.

**Open:** hardware validation on a physical AGM M7 is the frontier. QEMU exercises the boot path, not the MT6739's binary-only modem/WiFi/BT/GPS blobs. Several implemented capabilities aren't wired to the boot/service loop yet (tracked as the boot-wiring epic). Real radio I/O is hardware work; the boot degrades to a fail-closed loopback path when the data path is absent. A live Aletheia runtime bridge (`metaxu`) is future work — the protocol surface exists, nothing embeds a live agent runtime yet.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Method | Where to check |
|---|---|---|
| <span class="ok">Kernel boots to a ticking service loop under QEMU, every push</span> | CI runs the boot and asserts serviced ticks | `.github/workflows/ci.yml` in the repo |
| 92,913 lines Rust (code-only), 119,826 including comments | `tokei` against a local clone, 2026-07-20 | reproducible: `tokei` on a fresh clone |
| 14 workspace crates | crate count in `Cargo.toml` / `ls crates/` | reproducible on a fresh clone |
| ~2,964 test-attribute occurrences | `rg -c '#\[(tokio::)?test'`, 2026-07-20 | reproducible: same `rg` command on a fresh clone |

</div>

## Where to look

- Repo: [github.com/forkwright/thumos](https://github.com/forkwright/thumos)
- The CI workflow that runs the boot on every push: `.github/workflows/ci.yml`
- The kernel wiring audit, tracking what's compiled vs. what's reachable: `docs/KERNEL-WIRING-AUDIT.md`
