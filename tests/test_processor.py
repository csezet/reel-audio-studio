import unittest

from reel_audio.engine.processor import ProcessingSettings, _keep_segments, build_audio_filter


class ProcessorTests(unittest.TestCase):
    def test_keep_segments_removes_middle_of_long_silence(self):
        segs = _keep_segments(10.0, [(2.0, 5.0)], 0.2)
        self.assertEqual(len(segs), 2)
        self.assertAlmostEqual(segs[0][1], 2.1, places=3)
        self.assertAlmostEqual(segs[1][0], 4.9, places=3)

    def test_filter_contains_mastering_chain(self):
        f = build_audio_filter(ProcessingSettings())
        self.assertIn("afftdn", f)
        self.assertIn("acompressor", f)
        self.assertIn("loudnorm", f)
        self.assertIn("alimiter", f)

    def test_ai_denoise_skips_ffmpeg_denoiser(self):
        f = build_audio_filter(ProcessingSettings(), after_ai_denoise=True)
        self.assertNotIn("afftdn", f)

    def test_normalization_can_be_disabled(self):
        f = build_audio_filter(ProcessingSettings(auto_normalize=False))
        self.assertNotIn("loudnorm", f)
        self.assertIn("alimiter", f)


if __name__ == "__main__":
    unittest.main()
