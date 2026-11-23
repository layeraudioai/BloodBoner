# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import cache_manifest


STAGES = {
    "game_files": "stages/game_files",
    "boot_image": "stages/boot_image",
    "aot_code": "stages/aot_code",
    "textures": "stages/textures",
    "audio": "stages/audio",
}


class CacheManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "cache"
        self.root.mkdir()
        self.pkg = Path(self.temp.name) / "base.pkg"
        self.pkg.write_bytes(b"synthetic test input; not a real package")
        self._write_stages()

    def tearDown(self):
        self.temp.cleanup()

    def _write_stages(self):
        for name, rel in STAGES.items():
            stage_dir = self.root / rel
            stage_dir.mkdir(parents=True, exist_ok=True)
            (stage_dir / "output.bin").write_bytes((name + " output\n").encode())

    def _seal(self, profile=None, stages=None):
        stage_args = [f"{name}={rel}" for name, rel in (stages or STAGES).items()]
        profile_args = [f"{k}={v}" for k, v in (profile or {"texture.mips": "preserve"}).items()]
        return cache_manifest.seal(
            str(self.root), "switch1", "01.09", 1, "prototype-1",
            [str(self.pkg)], profile_args, stage_args,
        )

    def test_portable_c_consumer_verifies_hashes(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("no C compiler available for portable consumer integration test")
        executable = Path(self.temp.name) / "cache-consumer"
        source = Path(__file__).parent / "source" / "cache_consumer.c"
        subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-DBBR_CACHE_CONSUMER_STANDALONE", str(source), "-o", str(executable)],
                       check=True, capture_output=True, text=True)
        self._seal()
        valid = subprocess.run([str(executable), str(self.root), "switch1"], capture_output=True, text=True)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        mismatch = subprocess.run([str(executable), str(self.root), "switch2"], capture_output=True, text=True)
        self.assertNotEqual(mismatch.returncode, 0)
        manifest_path = self.root / cache_manifest.MANIFEST_NAME
        original_manifest = manifest_path.read_bytes()
        manifest_path.write_bytes(original_manifest + b" ")
        manifest_mismatch = subprocess.run([str(executable), str(self.root), "switch1"], capture_output=True, text=True)
        self.assertNotEqual(manifest_mismatch.returncode, 0)
        manifest_path.write_bytes(original_manifest)
        (self.root / STAGES["audio"] / "output.bin").write_bytes(b"corrupted")
        corrupt = subprocess.run([str(executable), str(self.root), "switch1"], capture_output=True, text=True)
        self.assertNotEqual(corrupt.returncode, 0)

    def test_seal_and_verify(self):
        manifest = self._seal()
        checked = cache_manifest.verify(str(self.root), [str(self.pkg)], "switch1")
        self.assertEqual(manifest["cache_key"], checked["cache_key"])
        self.assertEqual(set(checked["stages"]), set(STAGES))
        self.assertTrue((self.root / cache_manifest.MANIFEST_NAME).is_file())

    def test_index_mismatch_is_detected(self):
        self._seal()
        index = self.root / cache_manifest.INDEX_NAME
        index.write_text(index.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match the cache manifest"):
            cache_manifest.verify(str(self.root))

    def test_output_modification_is_detected(self):
        self._seal()
        (self.root / STAGES["textures"] / "output.bin").write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError, "failed size/hash verification"):
            cache_manifest.verify(str(self.root))

    def test_wrong_source_package_is_detected(self):
        self._seal()
        other = Path(self.temp.name) / "other.pkg"
        other.write_bytes(b"different source")
        with self.assertRaisesRegex(ValueError, "source PKG set"):
            cache_manifest.verify(str(self.root), [str(other)])

    def test_target_mismatch_is_detected(self):
        self._seal()
        with self.assertRaisesRegex(ValueError, "cache target"):
            cache_manifest.verify(str(self.root), expected_target="switch2")

    def test_profile_changes_cache_identity(self):
        first = self._seal(profile={"texture.mips": "preserve"})["cache_key"]
        second = self._seal(profile={"texture.mips": "none"})["cache_key"]
        self.assertNotEqual(first, second)

    def test_stage_keys_invalidate_only_asset_profile_dependents(self):
        first = self._seal(profile={"texture.mips": "preserve", "audio.codec": "lossless"})
        second = self._seal(profile={"texture.mips": "none", "audio.codec": "lossless"})
        for name in ("game_files", "boot_image", "aot_code", "audio"):
            self.assertEqual(first["stages"][name]["stage_key"], second["stages"][name]["stage_key"])
        self.assertNotEqual(first["stages"]["textures"]["stage_key"], second["stages"]["textures"]["stage_key"])

    def test_missing_required_stage_is_rejected(self):
        partial = {name: rel for name, rel in STAGES.items() if name != "audio"}
        with self.assertRaisesRegex(ValueError, "missing: audio"):
            self._seal(stages=partial)

    def test_path_traversal_in_manifest_is_rejected(self):
        self._seal()
        path = self.root / cache_manifest.MANIFEST_NAME
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["stages"]["aot_code"]["files"][0]["path"] = "../../outside.bin"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsafe relative path"):
            cache_manifest.verify(str(self.root))

    def test_publish_copies_verified_cache_and_rejects_overwrite(self):
        manifest = self._seal()
        destination = Path(self.temp.name) / "sd" / manifest["cache_key"]
        published = cache_manifest.publish(str(self.root), str(destination), "switch1")
        self.assertEqual(manifest["cache_key"], published["cache_key"])
        checked = cache_manifest.verify(str(destination), expected_target="switch1")
        self.assertEqual(manifest["cache_key"], checked["cache_key"])
        with self.assertRaisesRegex(ValueError, "destination already exists"):
            cache_manifest.publish(str(self.root), str(destination), "switch1")

    def test_publish_resumes_valid_partial_file(self):
        manifest = self._seal()
        destination = Path(self.temp.name) / "sd" / manifest["cache_key"]
        partial_root = destination.parent / f".{destination.name}.partial-{manifest['cache_key']}"
        rel = Path(STAGES["textures"]) / "output.bin"
        source = self.root / rel
        target = partial_root / rel
        target.parent.mkdir(parents=True)
        target.with_name(target.name + ".bloodboner-transfer-part").write_bytes(source.read_bytes()[:5])
        cache_manifest.publish(str(self.root), str(destination), "switch1")
        self.assertEqual(source.read_bytes(), (destination / rel).read_bytes())
        self.assertFalse(partial_root.exists())

    def test_publish_discards_corrupt_partial_prefix(self):
        manifest = self._seal()
        destination = Path(self.temp.name) / "sd" / manifest["cache_key"]
        partial_root = destination.parent / f".{destination.name}.partial-{manifest['cache_key']}"
        rel = Path(STAGES["audio"]) / "output.bin"
        target = partial_root / rel
        target.parent.mkdir(parents=True)
        target.with_name(target.name + ".bloodboner-transfer-part").write_bytes(b"wrong")
        cache_manifest.publish(str(self.root), str(destination), "switch1")
        self.assertEqual((self.root / rel).read_bytes(), (destination / rel).read_bytes())

    def test_failed_publish_does_not_create_destination(self):
        manifest = self._seal()
        destination = Path(self.temp.name) / "sd" / manifest["cache_key"]
        original = self.root / STAGES["audio"] / "output.bin"
        original.write_bytes(b"corrupted after sealing")
        with self.assertRaisesRegex(ValueError, "failed size/hash verification"):
            cache_manifest.publish(str(self.root), str(destination), "switch1")
        self.assertFalse(destination.exists())

    def test_cache_manifest_replacement_is_atomic_and_valid_json(self):
        self._seal()
        manifest_path = self.root / cache_manifest.MANIFEST_NAME
        self._seal(profile={"texture.mips": "high-quality"})
        self.assertTrue(json.loads(manifest_path.read_text(encoding="utf-8"))["cache_key"])
        self.assertFalse(list(self.root.glob(".cache-manifest.json.*.tmp")))


if __name__ == "__main__":
    unittest.main()
