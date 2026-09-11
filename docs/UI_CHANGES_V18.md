# UI changes v18 — primary action regression fix

- Fixed the blank **АВТОМАТИЧЕСКИ УЛУЧШИТЬ ЗВУК** button.
- Root cause: `AnimatedPrimaryButton.paintEvent()` referenced `QFont.SpacingType` without importing `QFont`, so the custom paint handler stopped after drawing the background and before drawing the icon/text.
- Added the missing `QFont` import.
- The primary action now remains clickable whenever no job is running, even if FFmpeg/FFprobe are unavailable. Its click handler can therefore show the existing diagnostic message instead of leaving a disabled/dead control.
- The button is disabled only while a processing/export job owns the UI.
