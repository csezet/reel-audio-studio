# UI v5 — Borderless outer edge

- Window layout outer margin: `10 px` -> `0 px`.
- Removed `QGraphicsDropShadowEffect` from `GlassShell`.
- `GlassShell` keeps only its subtle 1 px translucent border.
- Maximized and normal states both use zero outer gutter.
- Existing invisible `ResizeHandle` overlays remain active, so edge resizing is preserved.
