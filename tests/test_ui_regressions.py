import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UiRegressionTests(unittest.TestCase):
    def test_animated_primary_button_imports_qfont(self):
        source = (ROOT / 'reel_audio' / 'ui' / 'widgets.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == 'PySide6.QtGui':
                imported.update(alias.asname or alias.name for alias in node.names)
        self.assertIn('QFont', imported)
        self.assertIn('QFont.SpacingType.AbsoluteSpacing', source)

    def test_primary_action_stays_clickable_for_diagnostics(self):
        source = (ROOT / 'reel_audio' / 'ui' / 'main_window.py').read_text(encoding='utf-8')
        # The click handler itself handles missing FFmpeg, so the control must not be
        # disabled just because the runtime dependency is temporarily unavailable.
        self.assertNotIn('self.enhance_btn.setEnabled(self._ffmpeg_ready)', source)
        self.assertNotIn('self.enhance_btn.setEnabled(self._ffmpeg_ready and not running)', source)
        self.assertIn('if not self._ffmpeg_ready:', source)
        self.assertIn('FFmpeg/FFprobe не найдены', source)


if __name__ == "__main__":
    unittest.main()

