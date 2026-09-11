import unittest
from unittest.mock import patch

from reel_audio.engine import tools


class ToolTests(unittest.TestCase):
    @patch("reel_audio.engine.tools.os.name", "nt")
    @patch("reel_audio.engine.tools.available_encoders")
    def test_windows_prefers_media_foundation_encoder(self, encoders):
        encoders.return_value = {"h264_mf", "libx264", "mpeg4"}
        name, opts = tools.choose_video_encoder("ffmpeg")
        self.assertEqual(name, "h264_mf")
        self.assertIn("8M", opts)

    @patch("reel_audio.engine.tools.available_encoders")
    def test_encoder_falls_back_to_mpeg4(self, encoders):
        encoders.return_value = {"mpeg4"}
        name, _ = tools.choose_video_encoder("ffmpeg")
        self.assertEqual(name, "mpeg4")


if __name__ == "__main__":
    unittest.main()
