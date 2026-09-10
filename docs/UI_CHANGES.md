# Glass UI revision

This revision addresses the visual defects visible in the previous Windows screenshot.

- Removes the native OS title bar and replaces it with a custom title bar matching the reference layout.
- Adds functional minimize, maximize/restore and close buttons.
- Adds double-click maximize and native system drag/resize.
- Removes the accidental opaque background from every child `QWidget`, which caused dark rectangular strips behind labels and controls.
- Uses translucent RGBA surfaces only on the actual shell/panels/cards.
- Requests Windows 11 Desktop Acrylic through the documented DWM system-backdrop API when available.
- Uses a compact one-row six-card processing layout on normal desktop widths, so the Export section stays visible on common 16:9 displays.
- Adds persistent History/recent-files menu.
- Replaces text/Unicode pseudo-icons with consistent programmatically drawn vector icons.
- Adds an application `.ico` for the EXE and taskbar.
- Refines waveform contrast, time ruler and playback cursor.

Windows 11 build 22621+ is required for the documented Desktop Acrylic system backdrop. Older systems still receive the semi-transparent matte Qt fallback, but cannot be guaranteed to reproduce the same system blur material.

## Glass UI v4 — transparency and slider rendering fixes

- Replaced QSS/native sliders with a custom-painted `GlassSlider`. This removes the wide rectangular `sub-page` artifacts visible at some Windows DPI/scaling combinations.
- Timeline, volume and processing sliders now share the same thin 3–4 px glass track and circular handle.
- Reduced the opacity of the main shell, cards, controls and export panel so the desktop backdrop can actually show through.
- Extended the DWM frame through the full client area and kept the official Windows 11 `DWMSBT_TRANSIENTWINDOW` Desktop Acrylic request on build 22621+.
- Added an explicit transparent top-level palette in addition to `WA_TranslucentBackground` and `FramelessWindowHint`.
- Reduced the custom drop shadow opacity so it no longer looks like an opaque black frame around the glass surface.
