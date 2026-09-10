# UI Changes v8 — native Windows 11 window transitions

The custom translucent Qt frame now keeps the native Windows shell style bits (`WS_CAPTION`, `WS_THICKFRAME`, `WS_SYSMENU`, `WS_MINIMIZEBOX`, `WS_MAXIMIZEBOX`) while handling `WM_NCCALCSIZE` so no standard caption or border is painted. This gives DWM and the taskbar enough native window semantics to animate minimize/restore and maximize/restore like regular Windows applications.

The minimize/maximize/restore controls call Win32 `ShowWindow` on Windows. Other platforms fall back to Qt window-state APIs. DWM transitions are explicitly enabled per-window, but system-wide user accessibility preferences are respected.

References used for this implementation:
- Microsoft custom DWM frame documentation: https://learn.microsoft.com/windows/win32/dwm/customframe
- Microsoft DWMWINDOWATTRIBUTE / transitions: https://learn.microsoft.com/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute
- Qt QWidget nativeEvent and translucent-window documentation: https://doc.qt.io/qt-6/qwidget.html
- pyside-frameless (MIT), used as a design reference for PySide6 native event handling: https://github.com/PsinaDev/pyside-frameless
