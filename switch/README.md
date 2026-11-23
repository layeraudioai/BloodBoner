<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# Switch / Horizon bootstrap

This directory is the first, deliberately small Horizon OS bring-up target. It builds a homebrew NRO with devkitPro/libnx, prints a status screen, reads controller input, and attempts to mount the SD card. It is **not** Bloodborne and does not yet read PKGs, prepare assets, build the AOT cache, or load `libbbaot.so`. The intended product supports both PC-assisted first setup and a resumable on-console setup; see the architecture plan for the required gates.

The larger reuse assessment and runtime design are in [`docs/SWITCH_PORT_ARCHITECTURE.md`](../docs/SWITCH_PORT_ARCHITECTURE.md).

## Build the bootstrap NRO

Install devkitPro with the Switch/libnx toolchain and GNU make. On Windows, run `build-nx.bat` from the repository root for the Switch 1 profile, or `build-ounce.bat` for the Switch 2 profile. An optional first argument sets the output directory; by default the NRO is copied to `dist/bloodboner-switch1.nro` or `dist/bloodboner-switch2.nro`.

Equivalent make commands from this directory are `make TARGET_PROFILE=switch1` and `make TARGET_PROFILE=switch2`. Separate build directories and target names prevent one profile's object files from being reused for the other.

The Switch 2 script selects a profile label and cache target; it does not add a Switch 2-specific renderer/runtime or prove SDK support. You need a toolchain that actually supports the target. This checkout/container does not include devkitPro/libnx, so neither NRO has been built or hardware-tested here. Both are cache-verification bootstrap apps, not playable game ports.

## Shared setup-cache manifest (prototype)

`cache_manifest.py` defines the PC/Switch-shared cache contract. It streams SHA-256 over source PKGs and stage outputs, records a target/profile/runtime identity, and writes `cache-manifest.json` plus a compact `cache-index.tsv`. `verify` checks the source package set (when supplied), cache identity, target, output sizes and hashes, and exact agreement between the JSON manifest and TSV index. It does not extract or transform package contents. Cache paths are relative; source absolute paths are not recorded.

The NRO cache consumer reads the TSV index at `sdmc:/switch/bloodboner/cache/active`: it checks the build target, the index-to-JSON manifest hash, safe relative paths, required stage presence, and SHA-256 plus byte count for every indexed output. The portable C verifier has a host-side standalone test mode. The NRO still does **not** load or execute AOT code; a verified cache is not a playable game. Because this performs full-file hashing at launch, expect startup delay for large caches; progress is shown before hashing begins.

The first schema requires all five completed stage directories:

| Stage | Contents |
|---|---|
| `game_files` | extracted, merged game files |
| `boot_image` | normalized image consumed by the recompiler |
| `aot_code` | Horizon-target AOT artifact (currently an experimental ET_REL bundle, not loadable by the NRO) |
| `textures` | converted texture outputs and metadata |
| `audio` | converted audio outputs and metadata |

Example after a future builder has produced those directories (run from the repository root):

```sh
python3 switch/cache_manifest.py seal --root out/cache --target switch1 \
  --game-version 01.09 --runtime-abi 1 --tool-version dev \
  --source-pkg /path/to/base.pkg --source-pkg /path/to/update.pkg \
  --profile texture.mips=preserve --profile audio.codec=target-default \
  --stage game_files=stages/game_files --stage boot_image=stages/boot_image \
  --stage aot_code=stages/aot_code --stage textures=stages/textures \
  --stage audio=stages/audio
python3 switch/cache_manifest.py verify --root out/cache --target switch1 \
  --source-pkg /path/to/base.pkg --source-pkg /path/to/update.pkg
```

After sealing, `publish` copies only manifest-listed outputs, verifies them again, writes completion metadata last, and exposes the completed directory with a same-filesystem atomic rename. Transfers resume from verified per-file prefixes after interruption; a damaged prefix is discarded and recopied. It refuses to overwrite an existing destination. To prepare the NRO's default path directly, use `python3 switch/cache_manifest.py publish --root out/cache --destination /media/sd/switch/bloodboner/cache/active --target switch1`. If `active` already exists, choose a temporary destination, validate it, and arrange a safe replacement while the NRO is not running. This transports completed stages; it does not produce them.

The AOT compiler can emit an experimental `aarch64-none-elf` ET_REL object bundle; details and the build command are in [`docs/HORIZON_AOT_EXPERIMENT.md`](../docs/HORIZON_AOT_EXPERIMENT.md). Runtime bring-up includes the ABI-pinned [`GuestState`](runtime/guest_state.h), an exact-unit dispatcher (`runtime/bbr_runtime.c`), a prototype AArch64 ET_REL loader (`runtime/bbr_elf_loader.c`) and libnx JIT allocator adapter. The loader has only host-tested synthetic inputs; actual compiler bundles may use unsupported GOT/TLS/PLT relocations, and no real NRO load has been validated. The NRO does not bind loaded module metadata to the dispatcher. The PS4 pad service slice is described below; guest import routing, other PS4 services, and game CPU/GPU/audio runtimes remain absent. See [`runtime/README.md`](runtime/README.md) for status and validation limits.

An asset census is available for an already-extracted directory:

```sh
python3 switch/asset_inventory.py /path/to/extracted/game --out out/asset-inventory.json
```

For a narrow open-format subset, `asset_pipeline.py` produces `stages/textures` and `stages/audio`:

```sh
python3 switch/asset_pipeline.py /path/to/extracted/open-assets --out out/asset-stages --color-space srgb --astcenc astcenc
```

This requires Arm `astcenc`. PNG/JPEG images are encoded as single-level ASTC (default 4x4 blocks, `-thorough`); choose `--color-space linear` for linear data/normal maps, and do not mix color spaces in one invocation. PCM mono/stereo RIFF/WAVE files are copied unchanged to the audio stage. Unknown formats, compressed WAV and other file types fail closed rather than publishing incomplete stages. Keep original inputs in `game_files`; ASTC encoding is lossy. The stages are experimental and the NRO does not yet load them. This tool does not parse PKGs or decode Bloodborne's proprietary archives.

The census recognizes a limited set of signatures (PNG/JPEG/DDS/KTX/ASTC, WAV/Ogg/FSB/CRI); extensions alone are not treated as format proof. There is still no complete first-run builder: extracted game files, Horizon-runtime-compatible AOT and all game texture/audio formats are not yet produced as one usable cache. The NRO verifies files only; it does not execute the AOT or load these assets. Run the host-side tests with `python3 -m unittest discover -s switch -p 'test_*.py'`. The host tools use Python 3.10+ and the standard library.

## Controls

- **A**: toggle the informational screen.
- **Plus**: exit.

The screen reports SD status, scans `sdmc:/switch/bloodboner/incoming/` for a `.pkg` with PS4 PKG magic, and reports whether the published cache passed full file hashing. The PKG scan is signature-only: the NRO does not extract it. `platform/horizon_input.c` translates libnx Npad buttons/sticks into a platform-neutral snapshot, and `platform/ps4_pad.c` implements a first portable PS4 `PadData` service slice (init/open/close/read/info/vibration callback). `platform/horizon_pad.c` connects the two: a runtime caller can read a PS4-format report sampled from Horizon Npad input. The NRO initializes this bridge, but no guest import resolver or game loop calls it yet; this is not full PS4 pad/motion/touch/haptics emulation. The cache consumer reads outputs only for verification and never loads or executes them. Full hashing can take noticeable time on a large SD cache. The repository's PC PKG tool rejects retail-encrypted PS4 packages and supports only fake/homebrew PKGs; no retail decryption path is implemented. Keep game content and generated game code local; never package or distribute them.
