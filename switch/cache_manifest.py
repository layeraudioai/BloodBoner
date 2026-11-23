#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Seal and verify a portable first-run cache manifest.

This helper only hashes input package files and generated cache files. It does
not decrypt, unpack, compile, or transform game content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
MANIFEST_NAME = "cache-manifest.json"
INDEX_NAME = "cache-index.tsv"
CHUNK_SIZE = 4 * 1024 * 1024
STAGE_DEPENDENCIES = {
    "game_files": (),
    "boot_image": ("game_files",),
    "aot_code": ("boot_image",),
    "textures": ("game_files",),
    "audio": ("game_files",),
}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _safe_relpath(raw: str) -> PurePosixPath:
    p = PurePosixPath(raw.replace("\\", "/"))
    if not raw or not p.parts or p.is_absolute() or any(part in ("", ".", "..") for part in p.parts):
        raise ValueError(f"unsafe relative path: {raw!r}")
    if p.parts and ":" in p.parts[0]:
        raise ValueError(f"drive-qualified path is not allowed: {raw!r}")
    return p


def _inside(root: Path, rel: PurePosixPath) -> Path:
    candidate = root.joinpath(*rel.parts)
    # Resolve parent components without requiring the leaf to exist. This also
    # prevents a symlinked directory from redirecting a cache path outside root.
    root_real = root.resolve(strict=True)
    parent_real = candidate.parent.resolve(strict=True)
    if parent_real != root_real and root_real not in parent_real.parents:
        raise ValueError(f"path escapes cache root: {rel.as_posix()}")
    if candidate.is_symlink():
        raise ValueError(f"symlinks are not allowed in cache outputs: {rel.as_posix()}")
    return candidate


def _file_record(root: Path, rel: PurePosixPath) -> dict[str, Any]:
    path = _inside(root, rel)
    if not path.is_file():
        raise ValueError(f"expected a regular file: {rel.as_posix()}")
    size, digest = sha256_file(path)
    return {"path": rel.as_posix(), "size": size, "sha256": digest}


def _parse_pairs(items: list[str], option: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"{option} expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        if not key or not value or key in result:
            raise ValueError(f"invalid or duplicate {option} key: {key!r}")
        result[key] = value
    return dict(sorted(result.items()))


def _cache_identity(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": manifest["schema_version"],
        "target": manifest["target"],
        "game_version": manifest["game_version"],
        "runtime_abi": manifest["runtime_abi"],
        "tool_version": manifest["tool_version"],
        "profiles": manifest["profiles"],
        "source_packages": manifest["source_packages"],
    }


def _index_bytes(manifest: dict[str, Any]) -> bytes:
    manifest_bytes = canonical_json(manifest) + b"\n"
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    rows = ["BBRCACHE\t1", f"target\t{manifest['target']}", f"cache_key\t{manifest['cache_key']}",
            f"manifest_sha256\t{manifest_hash}"]
    for stage_name, stage in manifest["stages"].items():
        for record in stage["files"]:
            path = record["path"]
            if any(ord(ch) < 32 for ch in path):
                raise ValueError(f"control character in cache path: {path!r}")
            rows.append(f"file\t{stage_name}\t{path}\t{record['size']}\t{record['sha256']}")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _identity_key(manifest: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_cache_identity(manifest))).hexdigest()


def _stage_key(manifest: dict[str, Any], stage_name: str, prior_keys: dict[str, str]) -> str:
    dependencies = STAGE_DEPENDENCIES[stage_name]
    profile_prefix = {
        "aot_code": "cpu.",
        "textures": "texture.",
        "audio": "audio.",
    }.get(stage_name)
    stage_profiles = {
        key: value for key, value in manifest["profiles"].items()
        if profile_prefix is not None and key.startswith(profile_prefix)
    }
    payload = {
        "target": manifest["target"],
        "game_version": manifest["game_version"],
        "runtime_abi": manifest["runtime_abi"],
        "tool_version": manifest["tool_version"],
        "source_packages": manifest["source_packages"],
        "stage": stage_name,
        "profiles": stage_profiles,
        "depends_on": {name: prior_keys[name] for name in dependencies},
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def _parse_stage_spec(spec: str) -> tuple[str, PurePosixPath]:
    if "=" not in spec:
        raise ValueError(f"--stage expects NAME=RELATIVE_DIRECTORY, got {spec!r}")
    name, rel = spec.split("=", 1)
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"invalid stage name: {name!r}")
    return name, _safe_relpath(rel)


def seal(root_arg: str, target: str, game_version: str, runtime_abi: int,
         tool_version: str, source_args: list[str], profile_args: list[str],
         stage_args: list[str]) -> dict[str, Any]:
    root = Path(root_arg).resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"cache root is not a directory: {root}")
    if target not in ("switch1", "switch2"):
        raise ValueError("target must be switch1 or switch2")
    if runtime_abi < 1:
        raise ValueError("runtime ABI must be a positive integer")
    if not source_args:
        raise ValueError("provide at least one --source-pkg")
    if not stage_args:
        raise ValueError("provide all required --stage NAME=RELATIVE_DIRECTORY entries")

    source_records = []
    for source_arg in source_args:
        source = Path(source_arg)
        if not source.is_file():
            raise ValueError(f"source package is not a regular file: {source}")
        size, digest = sha256_file(source)
        source_records.append({"file": source.name, "size": size, "sha256": digest})
    source_records.sort(key=lambda x: (x["file"].casefold(), x["sha256"]))

    profile = _parse_pairs(profile_args, "--profile")
    stages: dict[str, Any] = {}
    all_output_paths: set[str] = set()
    for spec in stage_args:
        name, directory = _parse_stage_spec(spec)
        if name in stages:
            raise ValueError(f"duplicate stage: {name}")
        stage_path = _inside(root, directory)
        if not stage_path.is_dir():
            raise ValueError(f"stage directory does not exist: {directory.as_posix()}")
        records: list[dict[str, Any]] = []
        for current, dirs, files in os.walk(stage_path, followlinks=False):
            current_path = Path(current)
            for dirname in list(dirs):
                child = current_path / dirname
                if child.is_symlink():
                    raise ValueError(f"symlink in stage output: {child.relative_to(root).as_posix()}")
            for filename in files:
                file_path = current_path / filename
                if file_path.is_symlink() or not file_path.is_file():
                    raise ValueError(f"non-regular stage output: {file_path.relative_to(root).as_posix()}")
                rel = PurePosixPath(file_path.relative_to(root).as_posix())
                records.append(_file_record(root, rel))
        records.sort(key=lambda x: x["path"])
        if not records:
            raise ValueError(f"stage has no files: {name}")
        for record in records:
            if record["path"] in all_output_paths:
                raise ValueError(f"cache output appears in multiple stages: {record['path']}")
            all_output_paths.add(record["path"])
        stages[name] = {"directory": directory.as_posix(), "files": records}

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": target,
        "game_version": game_version,
        "runtime_abi": runtime_abi,
        "tool_version": tool_version,
        "profiles": profile,
        "source_packages": source_records,
        "stages": dict(sorted(stages.items())),
    }
    missing_stages = set(STAGE_DEPENDENCIES) - set(stages)
    unexpected_stages = set(stages) - set(STAGE_DEPENDENCIES)
    if missing_stages or unexpected_stages:
        detail = []
        if missing_stages:
            detail.append("missing: " + ", ".join(sorted(missing_stages)))
        if unexpected_stages:
            detail.append("unknown: " + ", ".join(sorted(unexpected_stages)))
        raise ValueError("cache must contain the required stages (" + "; ".join(detail) + ")")

    manifest["cache_key"] = _identity_key(manifest)
    stage_keys: dict[str, str] = {}
    for name in STAGE_DEPENDENCIES:
        stage = manifest["stages"][name]
        dependencies = list(STAGE_DEPENDENCIES[name])
        stage["depends_on"] = dependencies
        stage["stage_key"] = _stage_key(manifest, name, stage_keys)
        stage_keys[name] = stage["stage_key"]
    _atomic_write(root / MANIFEST_NAME, canonical_json(manifest) + b"\n")
    _atomic_write(root / INDEX_NAME, _index_bytes(manifest))
    return manifest


def _atomic_write(path: Path, data: bytes) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, path)
        # Persist the directory entry on POSIX when supported.
        try:
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def verify(root_arg: str, source_args: list[str] | None = None,
           expected_target: str | None = None) -> dict[str, Any]:
    root = Path(root_arg).resolve(strict=True)
    manifest_path = root / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {MANIFEST_NAME}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported or invalid cache manifest schema")
    required = ("target", "game_version", "runtime_abi", "tool_version", "profiles", "source_packages", "stages", "cache_key")
    if any(key not in manifest for key in required):
        raise ValueError("cache manifest is missing required fields")
    if manifest["cache_key"] != _identity_key(manifest):
        raise ValueError("cache identity key does not match manifest contents")
    if expected_target and manifest["target"] != expected_target:
        raise ValueError(f"cache target is {manifest['target']!r}, expected {expected_target!r}")

    if source_args is not None:
        actual = []
        for source_arg in source_args:
            source = Path(source_arg)
            if not source.is_file():
                raise ValueError(f"source package is not a regular file: {source}")
            size, digest = sha256_file(source)
            actual.append({"file": source.name, "size": size, "sha256": digest})
        actual.sort(key=lambda x: (x["file"].casefold(), x["sha256"]))
        if actual != manifest["source_packages"]:
            raise ValueError("source PKG set does not match the cache manifest")

    seen: set[str] = set()
    stages = manifest["stages"]
    if not isinstance(stages, dict) or set(stages) != set(STAGE_DEPENDENCIES):
        raise ValueError("manifest does not contain the complete required stage set")
    expected_stage_keys: dict[str, str] = {}
    for stage_name in STAGE_DEPENDENCIES:
        stage = stages[stage_name]
        if not isinstance(stage, dict) or not isinstance(stage.get("files"), list) or not stage["files"]:
            raise ValueError(f"invalid or empty stage record: {stage_name}")
        expected_dependencies = list(STAGE_DEPENDENCIES[stage_name])
        if stage.get("depends_on") != expected_dependencies:
            raise ValueError(f"invalid dependencies for stage: {stage_name}")
        expected_key = _stage_key(manifest, stage_name, expected_stage_keys)
        if stage.get("stage_key") != expected_key:
            raise ValueError(f"invalid cache key for stage: {stage_name}")
        expected_stage_keys[stage_name] = expected_key
        stage_dir = _safe_relpath(stage.get("directory", ""))
        for record in stage["files"]:
            file_rel = _safe_relpath(record.get("path", ""))
            if stage_dir not in file_rel.parents:
                raise ValueError(f"stage file is outside its declared directory: {file_rel.as_posix()}")
        for record in stage["files"]:
            rel = _safe_relpath(record.get("path", ""))
            normalized = rel.as_posix()
            if normalized in seen:
                raise ValueError(f"duplicate output path in manifest: {normalized}")
            seen.add(normalized)
            actual_record = _file_record(root, rel)
            if actual_record != record:
                raise ValueError(f"cache file failed size/hash verification: {normalized}")
    try:
        index_data = (root / INDEX_NAME).read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read {INDEX_NAME}: {exc}") from exc
    if index_data != _index_bytes(manifest):
        raise ValueError(f"{INDEX_NAME} does not match the cache manifest")
    return manifest


def _copy_resumable(source: Path, target: Path, expected_size: int, expected_hash: str) -> None:
    """Copy one file, resuming a valid prefix left by an interrupted transfer."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError(f"refusing symlink in partial cache: {target}")
    if target.exists():
        size, digest = sha256_file(target)
        if size == expected_size and digest == expected_hash:
            return
        target.unlink()

    partial = target.with_name(target.name + ".bloodboner-transfer-part")
    if partial.is_symlink():
        raise ValueError(f"refusing symlink in partial cache: {partial}")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > expected_size:
        partial.unlink()
        offset = 0

    # A partial may have been corrupted or belong to a different source. Check
    # its entire prefix against the source before trusting the resume offset.
    if offset:
        with source.open("rb") as src, partial.open("rb") as dst:
            remaining = offset
            while remaining:
                amount = min(CHUNK_SIZE, remaining)
                a, b = src.read(amount), dst.read(amount)
                if len(a) != amount or a != b:
                    partial.unlink()
                    offset = 0
                    break
                remaining -= amount

    with source.open("rb") as src, partial.open("ab" if offset else "wb") as dst:
        src.seek(offset)
        while True:
            chunk = src.read(CHUNK_SIZE)
            if not chunk:
                break
            dst.write(chunk)
        dst.flush()
        os.fsync(dst.fileno())

    size, digest = sha256_file(partial)
    if size != expected_size or digest != expected_hash:
        raise ValueError(f"copied cache output failed verification: {source.name}")
    os.replace(partial, target)


def publish(root_arg: str, destination_arg: str, expected_target: str | None = None) -> dict[str, Any]:
    """Resumably copy a verified cache, then atomically publish the directory."""
    source_root = Path(root_arg).resolve(strict=True)
    manifest = verify(str(source_root), expected_target=expected_target)
    destination = Path(destination_arg).absolute()
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"destination already exists; choose a new cache-key path: {destination}")

    # Keep the partial beside the final path so the last rename is same-volume
    # atomic. A stable name lets a later invocation resume files after a crash.
    temp_root = parent / f".{destination.name}.partial-{manifest['cache_key']}"
    if temp_root.is_symlink():
        raise ValueError(f"partial cache path is a symlink: {temp_root}")
    temp_root.mkdir(exist_ok=True)
    if not temp_root.is_dir():
        raise ValueError(f"partial cache path is not a directory: {temp_root}")

    expected_paths: set[str] = set()
    for stage in manifest["stages"].values():
        for record in stage["files"]:
            rel = _safe_relpath(record["path"])
            expected_paths.add(rel.as_posix())
            source = _inside(source_root, rel)
            target = temp_root.joinpath(*rel.parts)
            _copy_resumable(source, target, record["size"], record["sha256"])

    # Do not accidentally publish unrelated files left in or injected into the
    # resumable directory. Ignore only the known in-progress suffix.
    for current, dirs, files in os.walk(temp_root, followlinks=False):
        current_path = Path(current)
        for name in dirs:
            if (current_path / name).is_symlink():
                raise ValueError("symlinks are not allowed in partial cache")
        for name in files:
            item = current_path / name
            if item.is_symlink():
                raise ValueError("symlinks are not allowed in partial cache")
            relative = item.relative_to(temp_root).as_posix()
            transfer_suffix = ".bloodboner-transfer-part"
            if relative.endswith(transfer_suffix):
                if relative[:-len(transfer_suffix)] not in expected_paths:
                    raise ValueError(f"unexpected partial cache file: {relative}")
            elif relative not in expected_paths and relative not in (MANIFEST_NAME, INDEX_NAME):
                raise ValueError(f"unexpected file in partial cache: {relative}")

    # Copy the completion manifest last; a partial cache is never mistaken for
    # a ready one by a consumer that requires this file.
    _copy_resumable(source_root / MANIFEST_NAME, temp_root / MANIFEST_NAME,
                    (source_root / MANIFEST_NAME).stat().st_size,
                    sha256_file(source_root / MANIFEST_NAME)[1])
    _copy_resumable(source_root / INDEX_NAME, temp_root / INDEX_NAME,
                    (source_root / INDEX_NAME).stat().st_size,
                    sha256_file(source_root / INDEX_NAME)[1])
    verify(str(temp_root), expected_target=expected_target)
    os.replace(temp_root, destination)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    seal_cmd = commands.add_parser("seal", help="hash completed cache stages and atomically write the manifest")
    seal_cmd.add_argument("--root", required=True, help="cache root directory")
    seal_cmd.add_argument("--target", required=True, choices=("switch1", "switch2"))
    seal_cmd.add_argument("--game-version", required=True)
    seal_cmd.add_argument("--runtime-abi", type=int, required=True)
    seal_cmd.add_argument("--tool-version", required=True)
    seal_cmd.add_argument("--source-pkg", action="append", default=[], help="source package path; may be repeated")
    seal_cmd.add_argument("--profile", action="append", default=[], metavar="KEY=VALUE", help="asset/target profile; may be repeated")
    seal_cmd.add_argument("--stage", action="append", default=[], metavar="NAME=RELATIVE_DIRECTORY", help="completed output stage; may be repeated")

    verify_cmd = commands.add_parser("verify", help="verify every cache output and optionally the source packages")
    verify_cmd.add_argument("--root", required=True)
    verify_cmd.add_argument("--source-pkg", action="append", default=None, help="source package path; may be repeated")
    verify_cmd.add_argument("--target", choices=("switch1", "switch2"), help="require this target")

    inspect_cmd = commands.add_parser("inspect", help="print a cache manifest after validating its identity")
    inspect_cmd.add_argument("--root", required=True)

    publish_cmd = commands.add_parser("publish", help="copy a verified cache to a new destination, then atomically expose it")
    publish_cmd.add_argument("--root", required=True, help="completed cache directory")
    publish_cmd.add_argument("--destination", required=True, help="new destination directory, e.g. SD:/switch/bloodboner/cache/<cache-key>")
    publish_cmd.add_argument("--target", choices=("switch1", "switch2"), help="require this hardware target")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "seal":
            manifest = seal(args.root, args.target, args.game_version, args.runtime_abi,
                            args.tool_version, args.source_pkg, args.profile, args.stage)
            print(f"sealed {manifest['target']} cache: {manifest['cache_key']}")
        elif args.command == "verify":
            manifest = verify(args.root, args.source_pkg, args.target)
            print(f"verified {manifest['target']} cache: {manifest['cache_key']}")
        elif args.command == "publish":
            manifest = publish(args.root, args.destination, args.target)
            print(f"published {manifest['target']} cache: {manifest['cache_key']}")
        else:
            manifest = verify(args.root)
            print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError) as exc:
        print(f"cache manifest: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
