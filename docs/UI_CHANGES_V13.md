# UI changes v13 — Rounded caption controls

- Replaced the title-bar hover backplates that were drawn with `fillRect()`.
- Minimize, maximize/restore and close controls now use inset rounded backplates.
- Added 125 ms OutCubic hover fade (respects the existing “UI animations” setting).
- Close keeps a restrained red destructive hover, but no longer paints a square cell.
- Caption glyph strokes use rounded caps/joins and the maximize/restore outlines are rounded.
- Reduced caption-button footprint to 40×32 px and added small spacing/right padding.
