import unittest

from reel_audio.engine.vad import _speech_ranges_from_probs, intersect_intervals


class VadTests(unittest.TestCase):
    def test_intersection_requires_both_silence_and_non_speech(self):
        level_silence = [(1.0, 4.0), (6.0, 9.0)]
        non_speech = [(0.0, 2.0), (3.0, 7.0), (8.0, 10.0)]
        self.assertEqual(
            intersect_intervals(level_silence, non_speech),
            [(1.0, 2.0), (3.0, 4.0), (6.0, 7.0), (8.0, 9.0)],
        )

    def test_intersection_min_duration_filters_short_overlap(self):
        out = intersect_intervals([(1.0, 2.0)], [(1.8, 2.2)], min_duration=0.3)
        self.assertEqual(out, [])

    def test_probabilities_create_padded_speech_range(self):
        # 512 samples == 32 ms.  Ten speech frames are 320 ms (>250 ms).
        probs = [0.05] * 5 + [0.9] * 10 + [0.05] * 8
        ranges = _speech_ranges_from_probs(probs, len(probs) * 512)
        self.assertEqual(len(ranges), 1)
        start, end = ranges[0]
        self.assertLess(start, 5 * 512 / 16000)
        self.assertGreater(end, 15 * 512 / 16000)


if __name__ == "__main__":
    unittest.main()
