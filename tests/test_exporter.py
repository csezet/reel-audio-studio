import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reel_audio.engine.exporter import _atomic_copy, export_media
from reel_audio.engine.tools import CommandCancelled


class ExporterTests(unittest.TestCase):
    def test_atomic_copy_replaces_only_after_full_copy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source.mp4"
            dst = root / "target.mp4"
            src.write_bytes(b"abc" * 1000)
            dst.write_bytes(b"old")
            seen = []
            _atomic_copy(src, dst, progress_cb=seen.append)
            self.assertEqual(dst.read_bytes(), src.read_bytes())
            self.assertEqual(seen[-1], 100)
            self.assertFalse(any(p.name.startswith(".target_") for p in root.iterdir()))

    def test_atomic_copy_cancellation_does_not_replace_destination(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source.mp4"
            dst = root / "target.mp4"
            src.write_bytes(b"x" * (5 * 1024 * 1024))
            dst.write_bytes(b"original")
            calls = {"n": 0}

            def cancel():
                calls["n"] += 1
                return calls["n"] >= 2

            with self.assertRaises(CommandCancelled):
                _atomic_copy(src, dst, cancel_cb=cancel)
            self.assertEqual(dst.read_bytes(), b"original")

    @patch("reel_audio.engine.exporter.media_summary")
    def test_export_corrects_wrong_suffix_without_transcoding(self, summary):
        summary.return_value = {"duration": 1.0, "has_video": True, "has_audio": True}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "ready.mp4"
            src.write_bytes(b"ready")
            result = export_media(src, root / "named_wrong.wav", format_name="MP4 (H.264)", quality="Без доп. перекодирования")
            self.assertEqual(result.suffix, ".mp4")
            self.assertEqual(result.read_bytes(), b"ready")


if __name__ == "__main__":
    unittest.main()
