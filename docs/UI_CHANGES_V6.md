# UI changes v6 — True Transparent

- Removed the full-window `GlassShell` gradient/background plate.
- Removed the visible shell border and shell corner fill.
- Removed the 10 px shell bottom gutter.
- Disabled full-window DWM Acrylic/Mica and `DwmExtendFrameIntoClientArea` for this UI mode.
- Kept only DWM non-painting chrome hints (dark mode, rounded corner preference, no native border color).
- Kept translucent functional panels/cards and all window controls.
- The shell itself is fully transparent. Only the title bar keeps a practically invisible 1/255 alpha hit surface so dragging remains reliable without drawing a visible background.
