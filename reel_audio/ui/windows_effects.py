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


def apply_windows_backdrop(hwnd: int, acrylic: bool = True) -> bool:
    """Request a full-window DWM material on supported Windows versions.

    Windows 11 22H2+ gets the official system backdrop API.  We also extend the
    DWM frame across the full client area so a frameless Qt window can expose the
    material through transparent pixels.  Older Windows keeps Qt alpha
    transparency as a safe fallback (no undocumented composition API here).
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

        # Make the complete client area eligible for DWM composition/material.
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
        if _win_build() >= 22621:
            backdrop = ctypes.c_int(3 if acrylic else 2)
            hr = set_attr(hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
            return hr >= 0
    except Exception:
        return False
    return False
