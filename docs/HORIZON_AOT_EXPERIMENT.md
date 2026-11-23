<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Experimental Horizon AArch64 code-generation target

This adds a separate `aarch64-none-elf` target to the PC-side recompiler. The existing Android AArch64 and x86-64 targets remain unchanged. Do not treat this as a completed Switch port.

## Generate an ELF relocatable object bundle

Build `bb-recomp` with LLVM lowering enabled, then use the Horizon output mode:

```sh
bb-recomp --elf <your-supported-ELF-input> --target aarch64-none-elf --horizon-elf out/bloodborne-horizon.o --horizon-clang clang --horizon-lld ld.lld --horizon-sysroot <aarch64-none-elf-sysroot> -O1
```

For normal game-image preparation, supply the same supported inputs required by the existing compiler (`--boot`, `--game-dir`, or the corresponding `--elf`/module arguments). Only input packages that the existing project can lawfully and technically read are supported; this target does not decrypt retail packages.

The output is **ELF ET_REL** produced by `ld.lld -r -m aarch64elf`, not an NRO, NSP/NUP, shared library, or directly executable module. It contains AArch64 machine code, relocations, generated unit metadata and x87 helper code. Its unresolved `bbr_*` calls and helper imports intentionally remain for a future Horizon runtime/loader. No loader is implemented by this target, so the output cannot currently be executed by the NRO.

`--obj <base>` with `--target aarch64-none-elf` still emits individual relocatable objects (shards, table, helper object) and skips the final combine. `--so` remains Android/PC-only; using it with the Horizon target is rejected. `--json` remains Android player metadata and is not emitted for Horizon.

## Target baseline and caveats

The default Horizon codegen baseline is generic ARMv8-A (`+v8a,+fp-armv8,+neon`) without ARMv8.2 or LSE assumptions, chosen to avoid using instructions unsupported by the Switch 1 Cortex-A57. It is not a Switch 2 tuning profile. The input IR still models the guest x86-64 calling/guest-state ABI, and the artifact still depends on the runtime ABI described in `RECOMP_ABI.md`; changing the target triple does not port syscalls, graphics, audio, file services, or PS4 modules.

Required validation before relying on the artifact:

1. Build with a known LLVM/Clang and LLD toolchain; inspect the result with `llvm-readelf -h -r -s` and confirm `ELF64`, little-endian, `EM_AARCH64`, `ET_REL`, and only expected undefined runtime symbols.
2. Add a synthetic unit test linking one known AArch64 function, then run it through a Horizon loader with relocation checks and instruction-cache invalidation on Switch 1 hardware.
3. Define and implement the Horizon `GuestState`, `bbr_dispatch`, syscall, memory, FP, and exception ABI before attempting game execution.
4. Keep Android builds on the existing NDK target and run the current regression suite to confirm no target regression.

The helper object uses the selected Clang with `--target=aarch64-none-elf`; because its x87 helpers include `<math.h>`, supply a compatible target sysroot with `--horizon-sysroot` (or use a Clang configured with the correct sysroot). `ld.lld` must support `aarch64elf` relocatable linking. No devkitPro/LLVM Horizon toolchain is installed in the development sandbox, so this new backend is source-reviewed but not compiled or hardware-tested here.
