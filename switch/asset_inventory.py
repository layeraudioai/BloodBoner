#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only census of extracted game assets; intentionally does not decode PKGs."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "texture_candidate"),
    (b"\xff\xd8\xff", "image/jpeg", "texture_candidate"),
    (b"\xabKTX 11\xbb\r\n\x1a\n", "image/ktx1", "texture"),
    (b"\xabKTX 20\xbb\r\n\x1a\n", "image/ktx2", "texture"),
    (b"DDS ", "image/dds", "texture_candidate"),
    (b"\x13\xab\xa1\x5c", "image/astc", "texture"),
    (b"OggS", "audio/ogg", "audio_candidate"),
    (b"ID3", "audio/mp3", "audio_candidate"),
    (b"FSB5", "audio/fmod-bank", "audio_container"),
    (b"CRID", "video/cri-usm", "media_container"),
    (b"ADX ", "audio/cri-adx", "audio_candidate"),
    (b"@UTF", "audio/cri-utf", "audio_container"),
)


def classify(prefix: bytes, suffix: str) -> tuple[str, str]:
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WAVE":
        return "audio/wav", "audio_candidate"
    for signature, mime, role in SIGNATURES:
        if prefix.startswith(signature):
            return mime, role
    # A suffix is only a hint. Keep it separate so callers do not mistake it for a parse.
    return "application/octet-stream", "unknown" if not suffix else "unknown_ext:" + suffix.lower()


def census(root: Path) -> dict:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"not a directory: {root}")
    records = []
    for item in sorted(root.rglob("*")):
        if item.is_symlink():
            raise ValueError(f"symlinks are not allowed in asset input: {item.relative_to(root)}")
        if not item.is_file():
            continue
        rel = item.relative_to(root).as_posix()
        digest = hashlib.sha256()
        total = 0
        prefix = b""
        with item.open("rb") as stream:
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                if len(prefix) < 64:
                    prefix += block[:64 - len(prefix)]
                total += len(block)
                digest.update(block)
        kind, role = classify(prefix, item.suffix)
        records.append({"path": rel, "size": total, "sha256": digest.hexdigest(),
                        "media_type": kind, "role": role})
    if not records:
        raise ValueError("input directory contains no regular files")
    return {"schema_version": 1, "source_root_name": root.name,
            "files": records, "summary": _summary(records)}


def _summary(records: list[dict]) -> dict:
    summary: dict[str, dict[str, int]] = {}
    for record in records:
        group = record["role"].split(":", 1)[0]
        entry = summary.setdefault(group, {"files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += record["size"]
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="already-extracted, user-provided game directory")
    parser.add_argument("--out", type=Path, required=True, help="write inventory JSON to this path")
    args = parser.parse_args()
    try:
        report = census(args.input)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(report, sort_keys=True, indent=2) + "\n"
        temp = args.out.with_name(args.out.name + ".tmp")
        temp.write_text(data, encoding="utf-8")
        temp.replace(args.out)
        print(f"inventoried {len(report['files'])} files; report: {args.out}")
        print(json.dumps(report["summary"], sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"asset inventory failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
