<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Horizon runtime bring-up status

The surrounding `switch/platform/` layer maps Npad to a portable snapshot and to a tested subset of the Android port's PS4 PadData service (read/open/close/info and rumble callback). The NRO initializes this bridge, but the AOT guest import resolver does not route `scePad*` symbols to it; it is not yet game control integration.

This directory now has three distinct pieces:

- `guest_state.h` mirrors the Android port's AOT `GuestState` layout, with compile-time offsets/size checks and a reset routine. Its layout is pinned to `docs/RECOMP_ABI.md` and the Android source's `cpu/guest_state.h`; keep those in sync.
- `bbr_runtime.c` provides a small, single-threaded prototype dispatcher for a table of already-linked `bbr_units`. It checks sorted-table invariants, bounds-checks guest addresses, dispatches exact unit entries, respects the dirty-byte array, and reports unsupported paths through a fault callback. The C ABI helper names are present so a synthetic linked unit can exercise dispatch.
- `jit_code_memory_nx.c` is a libnx dual-mapped JIT-memory adapter using the libnx JIT API. It is a memory primitive only, not a loader.

This is **not a game runtime**. The dispatcher deliberately faults closed for dirty code (no x86 fallback CPU), guest traps, syscalls, CPUID/TSC/XGETBV and FP-rounding imports. The helper stubs do not implement PS4/Linux semantics and must not be treated as successful emulation. The current NRO does not bind an AOT table or call the dispatcher.

## Still required before game execution

1. A Horizon loader for the actual `ld.lld -r` ELF output: safe section placement, bounds/alignment checks, every emitted AArch64 relocation, undefined-symbol resolution, unwind policy, and relocation tests.
2. A runtime ABI verifier for ABI version, image hash, metadata and table consistency, plus a safe executable-memory route per Switch target. W^X and instruction-cache rules must be verified on hardware.
3. Guest image and module mapping, import resolution, PS4 service shims, syscall/thread/TLS support, exception/fault behavior, dirty-code fallback, and guest host-call marshalling.
4. Graphics and audio translation/backends, filesystem/save integration, and title lifecycle. Input still only controls the bootstrap screen; there is no Bloodborne gameplay input adapter.
5. A full synthetic runtime test and then real Switch 1/2 hardware validation. Switch 2 support is not established by the profile label or a Switch 1 build.

The host tests compile the guest-state layout and dispatcher against synthetic function tables. They do not validate the libnx JIT API, ELF loading, guest services, graphics/audio, or game boot. `bbr_runtime_abi.h` describes interfaces; it is not a substitute for the above systems.
