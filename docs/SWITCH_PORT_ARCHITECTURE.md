<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Horizon OS port: reuse assessment and proposed architecture

Status: **assessment / prototype stage**. The NRO bootstrap now verifies the integrity of a published cache index and its files, but this document does not claim the game currently runs on Switch or that a Horizon AOT artifact/runtime exists. Use only game files supplied by the player from their own copy. This repository contains no game executable or generated game code.

## Executive summary

The connected repository is **the Android rebuild/compiler tool**, not the Android game runtime. It translates Bloodborne's x86-64 image into AArch64 units and writes `libbbaot.so`; the Android app/runtime that loads that library, supplies the CPU state, implements PS4 services, and renders the game is a separate project (`ducvd89/Bloodborne-Android`). Consequently, adapting this repository alone cannot produce a playable Horizon port.

The strongest reuse is the **game-independent AOT pipeline**: FEX decode/lift, the IR lowering and AArch64 code generation, image analysis, game-specific function/variant data, and the established unit-table concepts. The weakest reuse is the **artifact and runtime boundary**: Android ELF/linker/bionic assumptions, Android's `libbbcpu.so` ABI, loader behavior, POSIX services, and Android-specific execution/testing. Do not simply rename `.so` to `.nro` or assume Horizon can `dlopen` the current artifact.

## Reuse inventory

| Existing area | Reuse | Notes / work needed |
|---|---|---|
| `src/discover.*`, `src/lifter.*`, FEX frontend, IR passes | High | Host-side compiler work is largely OS-neutral. Preserve its deterministic image inputs and validate generated instructions against both Switch CPU targets. |
| `src/lower_*`, `src/codegen.*`, LLVM AArch64 | High, with target constraints | The tool already emits AArch64. Make the CPU feature baseline explicit and avoid instructions absent on Switch 1 (Cortex-A57 / ARMv8-A baseline). Build and run tests on real hardware; Switch 2 needs its own measured profile. |
| `shared/prepare/`, boot image, game checks | Medium-high | Likely reusable if the port uses the same 1.09 game and exact module layout. A Horizon runtime must agree on image bytes, relocation/linking, system-module substitutes and hashes. |
| `variants/` and hook metadata | Medium-high | Game-version-specific fixes/hook addresses are valuable; hook implementations and semantics live in the runtime and must be reimplemented/revalidated. |
| `src/aot_json.*`, ABI and unit tables | Medium | Keep the conceptual metadata, but version a separate Horizon runtime ABI. The current JSON and `.so` checks encode Android artifact assumptions. |
| `src/bundle.*`, `bbrecomp.cmake`, `arm64/` package scripts | Low for Horizon | Android NDK, bionic, ELF linker stubs, static LLVM/LLD bundles and packaging are platform-specific. Add a separate target/output backend; don't contaminate existing Android builds. |
| `docs/RECOMP_ABI.md`, generated `bbr_*` exports | Medium | Useful starting point for runtime contract. Current ABI requires a loader, writable image-base/dirty state, dispatch callbacks, hook slots, and a compatible `GuestState`. Reuse requires a Switch runtime implementation and a new ABI identity. |
| Game runtime, graphics/audio/input/PS4 APIs | Not in this repository | Must be ported from the Android project or implemented separately. Likely the largest project area. Horizon GPU presentation and PS4 graphics/API translation are a major feasibility risk. |

## Proposed system architecture

1. **Two first-run paths, one deterministic pipeline:** accept only package formats the project can lawfully and technically read; never alter the source PKG. On PC, parse/extract, prepare the linked image, compile Switch-target AOT, and process assets using the PC's larger/faster resources, then copy the verified cache to SD. On Switch, run the same stages in bounded-memory, resumable chunks. The PC path is an accelerator, not a different output format: both paths must record compatible target, tool, source, and runtime-ABI identities. The PC recompiler now has an experimental `aarch64-none-elf` ET_REL output mode (see `docs/HORIZON_AOT_EXPERIMENT.md`); it is not executable until a Horizon loader/runtime exists. The NRO verifies caches but does not parse PKGs.
2. **Content-addressed setup cache:** derive a cache key from hashes of all source packages, game/version identity, compiler and asset-pipeline versions, target hardware profile, and runtime ABI. Stage work in a temporary directory; checkpoint completed extraction/AOT/asset chunks; verify sizes and hashes; write the completion manifest last and atomically rename into the ready-cache location. On launch, reuse only a fully verified matching cache. A killed build must resume safely; a changed input/profile invalidates only affected stages where dependency hashes prove that reuse is safe. Keep the original PKG read-only and preserve the prior valid cache until the new one completes.
3. **Asset optimization is a separate target pipeline:** inventory the real texture/audio formats first, then produce Horizon-supported GPU/audio formats and a manifest mapping source hashes to converted outputs. Preserve original extracted assets so conversion can be repeated. Prefer lossless transforms or high-quality encoders with measured quality/performance; use per-asset profiles and a runtime memory budget. Do not assume that the Android asset path or formats are compatible.
4. **Mipmaps are a quality/performance choice, not a blanket deletion:** removing the mip pyramid can save roughly one quarter of the fully-mipped texture storage, but reduces distant-image quality and can increase aliasing and texture bandwidth. The default should preserve existing useful mip levels or regenerate a suitable chain when needed. Offer a no-mipmap profile only after per-texture visual/performance tests show it is beneficial and memory measurements require it. “Highest quality” must mean the best tested target-format quality within the actual memory and performance budget, not simply largest uncompressed files.
5. **Target-specific AOT artifact:** define a Horizon artifact contract independently of `libbbaot.so`. Before selecting a format, prove how a same-process NRO/homebrew runtime can load and relocate a large generated module. Candidate approaches are (a) static inclusion/registration in a title NRO, (b) a supported homebrew dynamic-module loader, or (c) a carefully bounded custom ELF mapper. Choice is blocked on a runnable loader prototype and relocation audit. Do not use a custom loader until its memory permissions, cache maintenance, relocations, and safety are tested.
6. **Horizon launcher/runtime (new Switch-facing project):** NRO entrypoint; filesystem/content manager; game configuration; controller/input; lifecycle; logging/crash diagnostics; CPU dispatcher and the `GuestState`/unit-table ABI; guest memory mapping and PS4 service shims; then graphics/audio backends. Keep platform-facing code behind a narrow `HorizonPlatform` interface so Switch 1 and Switch 2 can have separate capabilities without forking compiler logic.
7. **Game services:** port/implement the runtime dependencies used by the Android port (CPU fallback/atomics, syscalls and threads, Fios/filesystem behavior, timing, memory, and graphics/audio). The guest image is not a standalone program: the Android runtime supplies many of these contracts.
8. **Hardware profiles:** start with a generic ARMv8-A code-generation baseline for Switch 1. The console has 4 GB physical RAM, but that does not mean an NRO can use all 4 GB; Horizon reserves memory and exposes a title/process-specific budget. Measure allocatable memory on the actual target and account for the game, compiler, caches, decompression buffers, textures, and audio concurrently. Treat Switch 2 as a separate, unverified profile until the chosen Horizon toolchain, loader, CPU feature set, and graphics APIs are confirmed on hardware. Atmosphère/Kaihen access is an environment assumption, not evidence that either target or an API is supported.

### First-run modes and cache policy

| Mode | First setup | Later launches |
|---|---|---|
| PC-assisted | PC reads the supported source package(s), performs extraction/AOT/asset work, and emits a verified Horizon cache bundle. | Copy/use the same cache on SD; NRO validates its manifest and source/profile key. |
| On-console | NRO performs the same steps in resumable chunks, with explicit free-space/RAM checks, progress, cancellation, and a safe restart point. This path is gated on Switch 1 memory and runtime benchmarks; 4 GB physical RAM alone is not proof it fits. | Reuse the verified cache, rebuilding only invalidated stages. |

The two modes must share artifact/manifest formats and deterministic build inputs. Prefer streaming and avoid keeping both full source and converted copies in RAM. Report estimated temporary disk requirements before starting, keep old cache until replacement is complete, and allow the user to choose a cache location. Do not write generated game code or assets into a distributable project/release.

For textures/audio, do not promise “highest quality” until the actual game formats and Horizon backend are known. First measure peak VRAM/system-memory use and inspect representative scenes. Evaluate target GPU block compression and audio transcodes against image/sound quality and decode cost; retain source assets and reversible conversion metadata.


### Delivery phases / gates

- **P0 — homebrew bring-up (started here):** build a minimal NRO that starts, handles input, and mounts SD.
- **P1 — cache protocol (partly implemented):** seal and publish a deterministic cache from a host tool; validate its index, manifest digest, paths and file hashes in a portable verifier. The NRO consumer now verifies data but does not load it.
- **P2 — loader proof:** load a small synthetic AArch64 module through a selected Horizon-supported mechanism; exercise relocations, RW/RX transitions, instruction-cache invalidation and unit-table lookups on Switch 1. Repeat on Switch 2 before claiming support.
- **P3 — runtime ABI:** implement and test a guest-state/dispatcher/runtime import ABI and prove it with synthetic code before any game artifact is generated.
- **P4 — PC first-run pipeline:** only after the ABI and loader are demonstrated, make a builder emit a target-compatible AOT artifact plus correctly converted assets. The PC compiler can now emit an experimental Horizon-target ET_REL bundle, but it is not executable; no Horizon runtime/loader or asset converter exists.
- **P5 — on-console parity:** port the same extraction/compile/asset stages with streaming, checkpoints, cancellation, storage estimation and measured memory budgets.
- **P6 — game bring-up and tuning:** prove image mapping, system-module shims, save/config paths, input, rendering, audio, texture quality/performance and stability on Switch 1; then validate a separate Switch 2 profile.

## First implementation in this repository

`switch/` is an isolated devkitPro/libnx bootstrap NRO: it shows startup/input/SD access and deliberately contains no game data or loader. It is a cheap first integration test and a place to grow Horizon-only code. It does **not** reuse the Android executable or prove that the AOT library can be loaded on Horizon.

## Risks / decisions that must be resolved

- Which legal, reproducible source image does the target runtime consume? Current build preparation creates an Android port-specific `boot-linked.bin`; that exact image may not match a new Horizon linker/runtime.
- What exact NRO/module loading mechanism and relocations are available for a ~125 MB code artifact? Verify on real hardware before designing around it.
- Which graphics backend can implement the PS4-facing GPU behavior at acceptable performance? A homebrew shell and CPU AOT success are not enough.
- How much usable application memory and CPU time are available per title on each console, and how does this vary by Horizon version?
- Does the toolchain distribute a Switch 2 target with the features and licensing needed? Build scripts and hardware validation must state exactly what they support.
- Which Android runtime sources can be reused? The required runtime project is not present in this checkout, so integration work should begin by mapping that project's boundaries and license terms.
