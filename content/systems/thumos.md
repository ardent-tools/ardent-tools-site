+++
title = "thumos"
description = "A bare-metal Rust phone OS for the AGM M7 - no Linux underneath. The kernel boots end-to-end under QEMU, and CI proves it on pushes to main and pull requests targeting main."
weight = 1
template = "system.html"

[extra]
gloss = "θυμός - the spirited part of the soul"
badge = "BOOTS UNDER EMULATION"
repo = "https://github.com/forkwright/thumos"
stack = "Rust · bare-metal armv7a · QEMU CI"
kanon_ci = true
license = "PolyForm Shield 1.0.0"

[extra.headline_claim]
claim = "Kernel boots end-to-end under QEMU"
receipt = "CI runs this boot on pushes to main and pull requests targeting main, then asserts the service loop ticks · .github/workflows/ci.yml"

[extra.demo]
system = "thumos"
action = "kernel boot"
target = "qemu-system-arm -machine virt"
cast = "/casts/thumos-boot.cast"
recipe = "/tapes/thumos-boot.driver.sh"
duration = "21s"
cols = 102
rows = 24
poster = "npt:0:19"
shows = "The same primary qemu-feature build and runner invocation used by CI, with the banner, boot-complete, and service-loop markers observed after a zero exit."
not_shows = "The complete CI sequence or hardware bring-up on the physical AGM M7. QEMU proves this boot path, not the modem/WiFi/BT/GPS vendor blobs."
fallback = [
  "$ cargo build --release --target armv7a-none-eabi --features qemu --jobs 8 && ok BUILD_OK",
  "THUMOS_BUILD_OK",
  "$ ../../scripts/qemu-runner.sh target/armv7a-none-eabi/release/thumos < /dev/null && ok BOOT_OK",
  "  THUMOS v0.1.0",
  "[init] Boot complete at 26 ms",
  "       6 / 18 subsystems OK",
  "THUMOS-QEMU: boot-complete",
  "[kardia] service loop running",
  "THUMOS-QEMU: service-loop ticks=50",
  "THUMOS_BOOT_OK",
  "$ # not shown: physical AGM M7 hardware - qemu proves the boot path, not the modem/wifi/bt/gps blobs",
]
transcript = '''
$ # thumos - bare-metal Rust kernel, no Linux, booting under qemu-system-arm
$ cargo build --release --target armv7a-none-eabi --features qemu --jobs 8 && ok BUILD_OK
    Finished `release` profile [optimized] target(s) in 0.05s
THUMOS_BUILD_OK
$ ../../scripts/qemu-runner.sh target/armv7a-none-eabi/release/thumos < /dev/null && ok BOOT_OK
thumos-qemu: kernel_main reached

================================
  THUMOS v0.1.0
  Rust OS for the AGM M7 (MT6739)
  THUMOS-BOOT-TRUST:DEV:8f98c164358c8ace (NOT PRODUCTION-TRUSTED)
================================

[init] MMU + caches
[init] Page allocator
       261632 pages free (1022 MB)
[init] Kernel heap
       slab: 0 allocs, 0 frees
[init] GIC
[init] Process subsystem
[init] Exceptions + timer
       Timer frequency: 62500000 Hz
[init] CSPRNG (ChaCha20)
       CSPRNG ready
[init] Watchdog (WDT, 5s)
       WDT skipped (qemu: no MT6739 WDT model)
[init] Device registry
       18 devices registered
[init] eMMC (MSDC0)
       Skipped (qemu: no MSDC model)
[init] Display (GC9306 240x320)
       Skipped (qemu: no DDP/DSI model)
[init] GPIO keypad
       Skipped (qemu: no KPD model)
[init] Secure boot verification
       Secure boot: DEGRADED (no boot medium -- trust not established; persistent data stays locked)
[init] Filesystem (LFS)
       Skipped (no eMMC)
[init] Passphrase entry
  WARN Passphrase entry refused (secure boot not established -- fail-closed)
[init] Encrypted filesystem
  WARN Encrypted mount skipped (no passphrase/eMMC)
[init] Audit log
  WARN Audit log deferred (secure boot not established -- fail-closed)
[init] Security mode (Daily)
       Security mode: Daily policy applied
[init] USB ACM serial
       Skipped (qemu: no MUSB model)
[init] CCCI modem
       Skipped (qemu: no CCCI/CLDMA model); phone functions disabled
[init] Power manager
       5 radios active per Daily policy (applied at security-mode init)
[init] Network WiFi readiness
  WARN WiFi data path unavailable; production network disabled
[init] Network loopback smoke (DHCP + DNS)
       Skipped (qemu: no network model -- #461)
[init] Bluetooth (BT HCI via WMT)
  WARN BT init failed: NotInitialized
       Bluetooth disabled
[init] GPS (via WMT)
  WARN GPS init failed: HardwareTimeout
       GPS disabled

[init] Boot complete at 78 ms
       6 / 18 subsystems OK
       NOTE: display unavailable, USB serial only
       NOTE: modem unavailable, no phone functions
       NOTE: network unavailable, no connectivity

[init] Spawning userspace processes
       Userspace: image-resident initramfs signature verified (boot anchor)
       /init spawned PL0 (PID 1)
       /shell spawned PL0 (PID 2)
       2 userspace ELF processes running
THUMOS-QEMU: boot-complete
[init] No debug console this boot; entering service loop
kardia: modem ready state=Registered
       Audit trail: interim session key (persistent key PENDING #217)
[karinit: hello from userspace
shell: hello from userspace
dia] service loop running
kardia: frame rendered painted_px=2191
kardia: clock src=manual wall=1735603200
kardia: audio ready sessions=1 mic_entries=1
kardia: statusbar net=Lte mode=D
kardia: sim iccid_len=19 sms_inbox=1 sim_ready=true signal_bars=3 operator_len=8 sms_sent=true
kardia: bt_audio sample_rate=44100 channels=2
kardia: netrat rat=Some(EUtran) net=Lte
kardia: heorte events=1 alarms=1 calendar_rows=2 timer_armed=true
kardia: firewall rules=1 allowed=1 denied=1 audit_events=2 chain=ok
kardia: reaped 2 fault-killed process(es)
kardia: nav Home -> Search
kardia: incoming call -> ringtone sessions=1
kardia: frame rendered painted_px=7934
kardia: nav Search -> Home
kardia: frame rendered painted_px=2191
THUMOS-QEMU: service-loop ticks=50
THUMOS_BOOT_OK
$ # not shown: physical AGM M7 hardware - qemu proves the boot path, not the modem/wifi/bt/gps blobs
'''
+++

## What it is

The AGM M7 is a $90 dumbphone - MediaTek MT6739, 1 GB of RAM, a 240x320 screen. thumos is an operating system for it, written from the kernel up in Rust. Kernel, memory manager, scheduler, userspace crates - all Rust, cross-compiled to bare metal, no Linux underneath any of it. The feature set targets secure communication and counter-surveillance: on-device detection for IMSI-catcher-shaped cell towers, MAC/IMEI randomization at the register level, encrypted storage, and a cellular modem firewalled at the driver boundary.

MediaTek ships the modem, WiFi, Bluetooth, and GPS radios as binary-only vendor blobs. Nothing replaces them with Rust, so thumos treats each as an untrusted peripheral behind a driver boundary.

## Decisions and trade-offs

### Prove the boot path in emulation before the hardware exists

On QEMU's `virt` board, the kernel reaches its service loop under `qemu-system-arm` in CI, without waiting for reliable access to physical AGM M7 hardware. A repeatable emulated run is worth more than an occasional manual test against real hardware, even though QEMU can't exercise the MT6739's actual radio silicon.

| Decision | Chose | Rejected | Cost accepted |
|---|---|---|---|
| Kernel language and target | Bare-metal Rust, kernel excluded from the main workspace for a clean `armv7a-none-eabi` cross-compile | Leaning on Linux's existing driver ecosystem | Every subsystem written and tested from scratch, no free drivers |
| Capability labeling | A capability counts as supported only once a boot or userspace call path reaches it | Calling a crate "supported" the moment it compiles | UI routing and Bluetooth A2DP are wired into the service loop and CI-smoked; GPS userspace and mesh/inbox remain open |

## What's solid / what's open

**Solid:** the kernel boots end-to-end under QEMU - MMU/cache setup, the GIC, the scheduler, the first timer interrupt, the CSPRNG, the init step for all 18 registered subsystems, the boot-to-service handoff, and a cooperative service loop running as PID 0 off a 100 Hz timer. CI gates the kernel's host test suite, the bare-metal cross-compile, and the boot itself. The kernel implements and unit-tests an OS core: memory management, interrupts and scheduling, IPC and signals, syscalls, a VFS, a CSPRNG, capabilities, power management, a watchdog.

**Wired witness:** the same QEMU CI boot observes a nonblank rendered screen, a Home → Search → Home UI round trip, and the Bluetooth audio state machine configured for A2DP at 44.1 kHz stereo. Those are real service-loop paths against emulated or synthetic devices, not proof of the physical display or radio silicon.

**Open:** encrypted storage, the audit log, and passphrase entry are gated on secure boot, which needs a boot medium QEMU does not model - the published cast shows all three fail closed. IMSI-catcher detection and MAC/IMEI randomization have no boot-path receipt. The modem firewall does (`kardia: firewall rules=1 allowed=1 denied=1 chain=ok`). Hardware validation on a physical AGM M7 has not run yet. QEMU exercises the boot path, not the MT6739's binary-only modem/WiFi/BT/GPS blobs. GPS initialization exists, but its userspace device path remains a stub. Mesh/inbox has no service-loop path. Real radio I/O is hardware work, and the boot degrades to a fail-closed loopback path when the data path is absent. A live aletheia runtime bridge (`metaxu`) is future work - the protocol surface exists, nothing embeds a live agent runtime yet.

## Numbers, and how they were measured

<div class="receipt-table-wrap">

| Claim | Reproduction method | Where to check |
|---|---|---|
| <span class="ok">Kernel boots to a ticking service loop under QEMU on pushes to `main` and pull requests targeting `main`</span> | CI runs the boot and asserts serviced ticks | `.github/workflows/ci.yml` at `77cc89906a52` |
| 6 of 18 registered subsystems reach OK under QEMU, 12 skip or warn for hardware QEMU does not model | read the boot log in the published cast | `/casts/thumos-boot.cast`, `[init] Boot complete` block |
| 92,913 Rust code lines; 119,826 physical Rust lines | `tokei -o json . | jq '.Rust | {code, comments, blanks, physical: (.code + .comments + .blanks)}'` at `77cc89906a52`, 2026-07-20 | run from that revision |
| 13 Cargo workspace members plus one deliberately excluded bare-metal kernel crate | `cargo metadata --no-deps --format-version 1 | jq '.workspace_members | length'` plus the workspace exclusion in `Cargo.toml` at `77cc89906a52` | run from that revision |
| ~2,964 test-attribute occurrences | `rg -o '#\[(tokio::)?test' --glob '*.rs' | wc -l` at `77cc89906a52`, 2026-07-20 | run from that revision |

</div>

## Where to look

- Repo: [github.com/forkwright/thumos](https://github.com/forkwright/thumos)
- The CI workflow that runs the boot: `.github/workflows/ci.yml`
- The kernel wiring audit, tracking what's compiled vs. what's reachable: `docs/KERNEL-WIRING-AUDIT.md`
