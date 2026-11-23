# SPDX-License-Identifier: GPL-3.0-or-later
import json
from pathlib import Path
import tempfile
import unittest

import asset_inventory


class AssetInventoryTests(unittest.TestCase):
    def test_classifies_signatures_not_suffixes_and_hashes_stream(self):
        self.assertEqual(asset_inventory.classify(b"RIFFxxxxWAVEdata", ".bin"),
                         ("audio/wav", "audio_candidate"))
        self.assertEqual(asset_inventory.classify(b"not a png", ".png"),
                         ("application/octet-stream", "unknown_ext:.png"))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            root.mkdir()
            (root / "looks.png").write_bytes(b"raw")
            (root / "voice.bin").write_bytes(b"OggS" + b"x" * 32)
            report = asset_inventory.census(root)
            self.assertEqual(len(report["files"]), 2)
            self.assertEqual(report["files"][0]["media_type"], "application/octet-stream")
            self.assertEqual(report["files"][1]["media_type"], "audio/ogg")
            self.assertEqual(report["summary"]["unknown_ext"]["files"], 1)
            self.assertEqual(report["summary"]["audio_candidate"]["files"], 1)

    def test_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "game"
            root.mkdir()
            outside = Path(temp) / "outside"
            outside.write_text("secret")
            (root / "link").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "symlinks are not allowed"):
                asset_inventory.census(root)

    def test_rejects_empty_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "contains no regular files"):
                asset_inventory.census(Path(temp))


if __name__ == "__main__":
    unittest.main()
