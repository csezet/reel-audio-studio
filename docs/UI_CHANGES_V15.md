# UI changes v15 — clickable plus

- The large `+` tile in the file drop area is now a real `QAbstractButton`.
- Clicking it opens the same `QFileDialog` as the **Открыть файл** button.
- Added pointer cursor, tooltip, keyboard focus/accessibility name, hover fade and pressed feedback.
- The previous non-interactive `IconBadge` remains available for decorative icons elsewhere.
