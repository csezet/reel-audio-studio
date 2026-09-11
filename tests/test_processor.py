import unittest

from reel_audio.engine.processor import (
    ProcessingSettings,
    _keep_segments,
    _parse_loudnorm_stats,
    build_audio_filter,
    build_pre_master_filter,
)


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

    def test_limiter_uses_real_minus_1_5_db_ceiling_without_auto_gain(self):
        f = build_audio_filter(ProcessingSettings(auto_normalize=False))
        self.assertIn("alimiter=limit=0.8414", f)
        self.assertIn("level=false", f)
        self.assertIn("latency=true", f)

    def test_ai_denoise_skips_ffmpeg_denoiser(self):
        f = build_audio_filter(ProcessingSettings(), after_ai_denoise=True)
        self.assertNotIn("afftdn", f)

    def test_normalization_can_be_disabled(self):
        f = build_audio_filter(ProcessingSettings(auto_normalize=False))
        self.assertNotIn("loudnorm", f)
        self.assertIn("alimiter", f)

    def test_voice_music_avoids_speech_specific_dsp(self):
        settings = ProcessingSettings(preset="Voice + Music", noise_removal=90, voice_presence=90)
        f = build_pre_master_filter(settings)
        self.assertIn("highpass=f=30", f)
        self.assertNotIn("afftdn", f)
        self.assertNotIn("equalizer", f)
        self.assertIn("acompressor", f)

    def test_loudnorm_json_is_parsed_for_second_pass(self):
        stderr = '''
        [Parsed_loudnorm_0] {
            "input_i" : "-22.31",
            "input_tp" : "-3.08",
            "input_lra" : "4.20",
            "input_thresh" : "-32.40",
            "output_i" : "-14.01",
            "output_tp" : "-1.50",
            "output_lra" : "3.80",
            "output_thresh" : "-24.10",
            "normalization_type" : "dynamic",
            "target_offset" : "0.01"
        }
        '''
        stats = _parse_loudnorm_stats(stderr)
        self.assertIsNotNone(stats)
        self.assertAlmostEqual(stats["input_i"], -22.31)
        self.assertAlmostEqual(stats["input_tp"], -3.08)
        self.assertAlmostEqual(stats["target_offset"], 0.01)
        second = build_audio_filter(ProcessingSettings(), loudnorm_stats=stats)
        self.assertIn("measured_I=-22.310", second)
        self.assertIn("measured_TP=-3.080", second)
        self.assertIn("linear=true", second)

    def test_invalid_loudnorm_json_falls_back_cleanly(self):
        self.assertIsNone(_parse_loudnorm_stats('noise {"input_i":"-inf"}'))


if __name__ == "__main__":
    unittest.main()
