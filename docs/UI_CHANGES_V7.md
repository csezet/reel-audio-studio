# UI changes v7

- Restored one coherent semi-transparent grey window background.
- Added custom `GlassShell.paintEvent()` with an antialiased rounded `QPainterPath`.
- The glass fill and 1 px border are painted entirely inside the widget rectangle.
- Kept top-level `WA_TranslucentBackground` and zero outer layout margins.
- No external drop shadow or full-window DWM Acrylic/Mica layer.
- Title bar is transparent so it cannot paint square pixels over rounded corners.
