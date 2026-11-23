<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Horizon runtime bring-up status

This directory contains the shared AOT C ABI declarations (`bbr_runtime_abi.h`) and a small libnx dual-mapped JIT memory adapter (`jit_code_memory_nx.c`). It is **not** an ELF loader or guest CPU runtime. The adapter uses libnx `jitCreate`/`jitTransitionToExecutable`/`jitClose`, which select the available CodeMemory or supported process-memory mechanism and fail if JIT is unavailable; it preserves separate RW and RX views and delegates cache maintenance to libnx. Keeping the distinction explicit prevents an experimental `aarch64-none-elf` ET_REL file from being mistaken for runnable code.

## Runtime contract carried forward

The compiler emits one function per unit: `void bbr_<guest-vaddr>(GuestState*)`. The table module exports sorted `bbr_units[]`, image-relative addresses and unit metadata, ABI version 2, and a writable `bbr_image_base`. The lowered code imports the helpers declared in `bbr_runtime_abi.h`. The authoritative semantics are in [`../../docs/RECOMP_ABI.md`](../../docs/RECOMP_ABI.md).

The Android runtime is not in this checkout. Before a Horizon runtime can execute anything, the port must implement and test:

1. The exact `GuestState` layout, AArch64 host-call convention, guest x86 register/flags state, and version checks.
2. A loader for the actual `ld.lld -r` ELF output, including section placement, all emitted AArch64 relocations, undefined-symbol resolution, unwind/exception policy, and bounds checking.
3. A Horizon-approved executable-memory strategy. Do not assume RWX heap is allowed: choose the supported NRO/NSO/module or JIT mapping route for each target, enforce W^X, and flush the instruction cache after relocation.
4. Image and linked-module mapping, PS4 syscall/service shims, guest faults/signals, dirty units, fallback CPU coverage, thread/TLS and guest host-call marshalling.
5. GPU, audio, input, storage, save and window/surface integration. A CPU AOT unit is not a game runtime by itself.

The current NRO only validates file hashes; it does not use the JIT adapter, map an AOT object, resolve imports, or execute cache output. `bbr_runtime_abi.h` is declaration-only and must not be linked as though it supplied the imports. The adapter's lifecycle is host-tested with a libnx mock, but not compiled against devkitPro or run on hardware. Next runtime gate: connect an ET_REL loader to the RW/RX allocator, support every relocation emitted by the compiler, implement all imports and image mapping, then test a synthetic function on Switch 1 and repeat on Switch 2.
