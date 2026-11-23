# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import tempfile
import wave
import unittest

import asset_pipeline


class AssetPipelineTests(unittest.TestCase):
    def _write_wav(self, path: Path):
        with wave.open(str(path), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(48000)
            stream.writeframes(b"\0\0" * 8)

    def _fake_encoder(self, path: Path):
        path.write_text(
            "#!/usr/bin/env python3\n"
            "import pathlib,sys\n"
            "dst=pathlib.Path(sys.argv[3])\n"
            "header=bytes([0x13,0xab,0xa1,0x5c,4,4,1,1,0,0,1,0,0,1,0,0])\n"
            "dst.write_bytes(header+b'\\0'*16)\n",
            encoding="utf-8")
        path.chmod(0o755)

    def test_builds_astc_single_level_and_pcm_passthrough_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input"
            source.mkdir()
            # The mock encoder only needs the PNG signature for this command-contract test.
            (source / "tex.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"fixture")
            self._write_wav(source / "voice.wav")
            encoder = root / "astcenc-mock"
            self._fake_encoder(encoder)
            output = root / "out"
            report = asset_pipeline.build_stages(source, output, str(encoder),
                                                "4x4", "srgb", "-thorough")
            astc = output / "stages/textures/tex.astc"
            wav = output / "stages/audio/voice.wav"
            self.assertTrue(astc.is_file())
            self.assertEqual(wav.read_bytes(), (source / "voice.wav").read_bytes())
            self.assertEqual(report["textures"][0]["mip_levels"], 1)
            self.assertFalse(report["audio"][0]["transcoded"])
            self.assertTrue((output / "stages/audio/asset-pipeline.json").is_file())

    def test_rejects_non_pcm_wav(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / "bad.wav"
            p.write_bytes(b"RIFFxxxxWAVE" + b"not-a-wav")
            with self.assertRaisesRegex(ValueError, "invalid or unsupported WAV"):
                asset_pipeline._validate_pcm_wav(p)

    def test_refuses_unknown_formats_instead_of_publishing_partial_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "input"
            source.mkdir()
            (source / "tex.png").write_bytes(b"\x89PNG\r\n\x1a\n")
            self._write_wav(source / "voice.wav")
            (source / "packed.bin").write_bytes(b"unknown")
            encoder = root / "astcenc-mock"
            self._fake_encoder(encoder)
            output = root / "out"
            with self.assertRaisesRegex(ValueError, "unhandled asset formats"):
                asset_pipeline.build_stages(source, output, str(encoder))
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
