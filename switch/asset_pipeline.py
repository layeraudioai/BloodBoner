#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Convert a narrow set of already-extracted open assets into prototype Switch stages."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

IMAGE_TYPES = {"image/png", "image/jpeg"}
AUDIO_TYPES = {"audio/wav"}


def sha256(path: Path) -> tuple[int, str]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            h.update(block)
    return size, h.hexdigest()


def _validate_pcm_wav(path: Path) -> None:
    try:
        with wave.open(str(path), "rb") as stream:
            if stream.getcomptype() != "NONE" or stream.getnchannels() not in (1, 2):
                raise ValueError(f"only uncompressed mono/stereo PCM WAV is supported: {path}")
            if stream.getsampwidth() not in (1, 2, 3, 4) or stream.getframerate() <= 0:
                raise ValueError(f"unsupported PCM WAV parameters: {path}")
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"invalid or unsupported WAV file: {path}: {exc}") from exc


def _run_astcenc(encoder: str, src: Path, dst: Path, block: str,
                 color_space: str, quality: str) -> None:
    profile = "-cs" if color_space == "srgb" else "-cl"
    command = [encoder, profile, str(src), str(dst), block, quality, "-silent"]
    subprocess.run(command, check=True)
    if not dst.is_file() or dst.stat().st_size <= 16:
        raise ValueError(f"ASTC encoder produced no valid-looking output for {src}")
    with dst.open("rb") as stream:
        header = stream.read(16)
    # ASTC file magic is 13 AB A1 5C; dimensions must be nonzero.
    if len(header) != 16 or header[:4] != bytes((0x13, 0xAB, 0xA1, 0x5C)):
        raise ValueError(f"ASTC encoder output has an invalid .astc header: {dst}")
    if header[4:7] == b"\0\0\0" or header[7:10] == b"\0\0\0" or header[10:13] == b"\0\0\0":
        raise ValueError(f"ASTC encoder output has zero dimensions: {dst}")


def build_stages(input_root: Path, output_root: Path, encoder: str,
                 block: str = "4x4", color_space: str = "srgb",
                 quality: str = "-thorough") -> dict:
    from asset_inventory import census
    input_root = input_root.resolve(strict=True)
    output_root = output_root.resolve()
    if not input_root.is_dir():
        raise ValueError("asset input must be an extracted directory")
    if output_root == input_root or input_root in output_root.parents:
        raise ValueError("output directory must not be inside the source tree")
    inventory = census(input_root)
    texture_inputs = [r for r in inventory["files"] if r["media_type"] in IMAGE_TYPES]
    audio_inputs = [r for r in inventory["files"] if r["media_type"] in AUDIO_TYPES]
    unsupported = [r for r in inventory["files"]
                   if r["media_type"] not in IMAGE_TYPES | AUDIO_TYPES]
    if unsupported:
        examples = ", ".join(f"{r['path']} ({r['media_type']})" for r in unsupported[:8])
        raise ValueError("unhandled asset formats; refusing to publish incomplete stages: " + examples)
    if not texture_inputs or not audio_inputs:
        raise ValueError("need at least one PNG/JPEG texture and one RIFF/WAVE audio file")
    for record in audio_inputs:
        _validate_pcm_wav(input_root / record["path"])
    resolved_encoder = shutil.which(encoder)
    if not resolved_encoder:
        raise ValueError(f"ASTC encoder not found: {encoder}")

    output_root.mkdir(parents=True, exist_ok=True)
    # Build in sibling temporary directories so a failure never replaces a previous result.
    output_root.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=output_root.name + ".building-",
                                      dir=output_root.parent))
    try:
        texture_root = temp_root / "stages" / "textures"
        audio_root = temp_root / "stages" / "audio"
        texture_root.mkdir(parents=True)
        audio_root.mkdir(parents=True)
        texture_records = []
        for record in texture_inputs:
            relative = Path(record["path"])
            src = input_root / relative
            out_rel = relative.with_suffix(".astc")
            dst = texture_root / out_rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            _run_astcenc(resolved_encoder, src, dst, block, color_space, quality)
            size, digest = sha256(dst)
            texture_records.append({"source": record["path"], "source_sha256": record["sha256"],
                                    "output": out_rel.as_posix(), "size": size, "sha256": digest,
                                    "format": "ASTC-4x4" if block == "4x4" else f"ASTC-{block}",
                                    "mip_levels": 1, "color_space": color_space,
                                    "quality": quality})
        audio_records = []
        for record in audio_inputs:
            relative = Path(record["path"])
            src = input_root / relative
            dst = audio_root / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            size, digest = sha256(dst)
            audio_records.append({"source": record["path"], "source_sha256": record["sha256"],
                                 "output": relative.as_posix(), "size": size, "sha256": digest,
                                 "format": "WAV passthrough", "transcoded": False})
        report = {
            "schema_version": 1,
            "pipeline": "switch-open-assets-prototype-1",
            "source_root_name": input_root.name,
            "texture_profile": {"encoder": resolved_encoder, "block": block,
                                 "color_space": color_space, "quality": quality,
                                 "mip_policy": "single-level-output"},
            "textures": texture_records,
            "audio": audio_records,
            "limitations": [
                "This is not a Bloodborne archive decoder; only extracted PNG/JPEG and PCM-compatible RIFF/WAVE inputs are accepted.",
                "ASTC compression is lossy; original source files should remain in the separate game_files stage.",
                "WAV data is copied unchanged; no audio optimization or runtime decoder is included.",
                "ASTC output must be validated with the target Switch GPU/runtime before use."
            ]
        }
        report_data = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
        (texture_root / "asset-pipeline.json").write_bytes(report_data)
        (audio_root / "asset-pipeline.json").write_bytes(report_data)
        # Atomic publish of a new output only; don't destroy a previous usable cache.
        if any(output_root.iterdir()):
            raise ValueError(f"output directory is not empty; refusing replacement: {output_root}")
        output_root.rmdir()
        temp_root.rename(output_root)
        return report
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="already-extracted assets directory")
    parser.add_argument("--out", type=Path, required=True, help="new, empty output-root directory")
    parser.add_argument("--astcenc", default="astcenc", help="Arm astcenc executable")
    parser.add_argument("--block", choices=("4x4", "5x5", "6x6"), default="4x4")
    parser.add_argument("--color-space", choices=("srgb", "linear"), required=True,
                        help="choose per asset class; sRGB is not appropriate for normal/data maps")
    parser.add_argument("--quality", choices=("-medium", "-thorough", "-verythorough"),
                        default="-thorough")
    args = parser.parse_args()
    try:
        report = build_stages(args.input, args.out, args.astcenc, args.block,
                              args.color_space, args.quality)
        print(f"built prototype stages: {len(report['textures'])} texture(s), "
              f"{len(report['audio'])} WAV file(s) -> {args.out}")
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"asset stage build failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
