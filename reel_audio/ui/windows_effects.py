from __future__ import annotations

import ctypes
import platform
import sys
from ctypes import wintypes


class _MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def _win_build() -> int:
    if sys.platform != "win32":
        return 0
    try:
        return int(platform.version().split(".")[-1])
    except Exception:
        return 0


def apply_windows_backdrop(hwnd: int, acrylic: bool = True, material: bool = True) -> bool:
    """Apply optional DWM chrome/material on supported Windows versions.

    With ``material=False`` only non-painting chrome hints (dark mode, rounded
    corner preference and no native border color) are requested.  Crucially, the
    DWM frame is not extended and Acrylic/Mica is not applied, so Qt alpha-zero
    regions can remain visually transparent.
    """
    if sys.platform != "win32" or not hwnd:
        return False

    try:
        dwmapi = ctypes.WinDLL("dwmapi")
        set_attr = dwmapi.DwmSetWindowAttribute
        set_attr.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        set_attr.restype = ctypes.c_long

        extend_frame = dwmapi.DwmExtendFrameIntoClientArea
        extend_frame.argtypes = [wintypes.HWND, ctypes.POINTER(_MARGINS)]
        extend_frame.restype = ctypes.c_long

        # Full-window DWM composition/material is optional.  For the
        # TrueTransparent UI we intentionally do NOT extend the DWM frame: doing
        # so paints Acrylic/Mica into pixels that Qt otherwise leaves transparent.
        if material:
            margins = _MARGINS(-1, -1, -1, -1)
            extend_frame(hwnd, ctypes.byref(margins))

        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        dark = ctypes.c_int(1)
        set_attr(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))

        # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
        rounded = ctypes.c_int(2)
        set_attr(hwnd, 33, ctypes.byref(rounded), ctypes.sizeof(rounded))

        # DWMWA_BORDER_COLOR = 34, DWMWA_COLOR_NONE = 0xFFFFFFFE
        no_border = wintypes.DWORD(0xFFFFFFFE)
        set_attr(hwnd, 34, ctypes.byref(no_border), ctypes.sizeof(no_border))

        # DWMWA_SYSTEMBACKDROP_TYPE = 38 (Windows 11 build 22621+)
        # 3 = DWMSBT_TRANSIENTWINDOW -> Desktop Acrylic
        # 2 = DWMSBT_MAINWINDOW      -> Mica
        if material and _win_build() >= 22621:
            backdrop = ctypes.c_int(3 if acrylic else 2)
            hr = set_attr(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
            return hr >= 0
        # Chrome attributes were applied, but no full-window material was requested.
        return False
    except Exception:
        return False
    return False


# Native shell integration --------------------------------------------------------------
# Keep normal top-level window capabilities at the Win32 level while Qt paints the
# complete client area itself. This lets DWM/taskbar treat the app like a regular
# captioned, resizable window and preserves the Windows minimize/restore transitions.
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9

WM_NCCALCSIZE = 0x0083


def enable_native_window_animations(hwnd: int) -> bool:
    """Restore native Windows shell/DWM transitions for our custom-frame window.

    Qt's ``FramelessWindowHint`` is kept because it is required for translucent
    top-level widgets on Windows.  We then restore the Win32 style bits that mark
    the HWND as a normal captioned/resizable application window.  ``MainWindow``
    consumes ``WM_NCCALCSIZE`` so the native caption/border is never painted.
    """
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        get_style = user32.GetWindowLongPtrW
        set_style = user32.SetWindowLongPtrW
        get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t

        style = int(get_style(hwnd, GWL_STYLE))
        wanted = WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        if (style & wanted) != wanted:
            ctypes.set_last_error(0)
            previous = set_style(hwnd, GWL_STYLE, style | wanted)
            if previous == 0 and ctypes.get_last_error() != 0:
                return False

        # Frame style values are cached by Windows. SWP_FRAMECHANGED forces a fresh
        # non-client calculation, which our nativeEvent turns into a full client area.
        set_pos = user32.SetWindowPos
        set_pos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        set_pos.restype = wintypes.BOOL
        flags = SWP_FRAMECHANGED | SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE
        if not set_pos(hwnd, None, 0, 0, 0, 0, flags):
            return False

        # Explicitly request DWM transitions to be enabled. This does not override
        # a user's global Accessibility/Windows animation preference.
        try:
            dwmapi = ctypes.WinDLL("dwmapi")
            set_attr = dwmapi.DwmSetWindowAttribute
            set_attr.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            set_attr.restype = ctypes.c_long
            transitions_disabled = wintypes.BOOL(False)
            set_attr(hwnd, 3, ctypes.byref(transitions_disabled), ctypes.sizeof(transitions_disabled))
        except Exception:
            pass
        return True
    except Exception:
        return False


def show_window_native(hwnd: int, command: int) -> bool:
    """Ask the Windows shell to minimize/maximize/restore this HWND natively."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        show_window = user32.ShowWindow
        show_window.argtypes = [wintypes.HWND, ctypes.c_int]
        show_window.restype = wintypes.BOOL
        show_window(hwnd, command)
        return True
    except Exception:
        return False


def is_nccalcsize_message(event_type, message) -> bool:
    """Return True for a Windows ``WM_NCCALCSIZE`` native Qt event."""
    if sys.platform != "win32":
        return False
    try:
        # PySide passes a QByteArray-like object and a pointer wrapper.  ``bytes``
        # is robust across current PySide6 versions; ``int(message)`` yields MSG*.
        if bytes(event_type) != b"windows_generic_MSG":
            return False
        msg = wintypes.MSG.from_address(int(message))
        return int(msg.message) == WM_NCCALCSIZE
    except Exception:
        return False
