# UI changes v11

- Replaced the black native `QMessageBox` opened by Settings with an in-app glass settings dialog.
- Settings now shows component status cleanly and provides a real UI option for enabling/disabling interface animations.
- Removed the bottom-right footer badges/status text (`FFmpeg ready / local processing / no browser`).
- Increased the large export icon next to the export title from 34 px to 44 px and enlarged its container.
- Added smooth hover animation to processing cards.
- Added smooth hover and selection transitions to preset tiles.
- Added animated toggle-knob motion using `QPropertyAnimation` with an OutCubic easing curve.
- Preserved the existing Windows 11 native window animations and clipped translucent background.
