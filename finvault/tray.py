"""Optional Windows system-tray icon built on ctypes.

FinVault has no third-party dependencies, so the tray icon talks to the Win32
shell directly (``Shell_NotifyIconW``) from a small background thread with its
own message loop. Importing this module on other platforms is safe: ``start``
returns ``None`` and the app simply runs without a tray icon.

Menu: **Open FinVault** and **Quit FinVault**. Left double-click opens the UI.
"""
from __future__ import annotations

import ctypes
import logging
import sys
import threading
from pathlib import Path
from typing import Callable

from .config import APP_DIR, RESOURCE_DIR

log = logging.getLogger("finvault")

TIP_TEXT = "FinVault - double-click to open. Right-click to quit."


def start(url: str, on_open: Callable[[], None], on_quit: Callable[[], None]):
    """Create the tray icon in a daemon thread. Returns None when unavailable."""
    if sys.platform != "win32":
        return None
    try:
        icon = TrayIcon(url=url, on_open=on_open, on_quit=on_quit)
        return icon if icon.start() else None
    except Exception:  # noqa: BLE001 - the tray is a convenience, never fatal
        log.exception("Tray icon unavailable")
        return None


if sys.platform == "win32":  # pragma: no branch - platform specific
    from ctypes import wintypes

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(
        LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )

    WM_NULL = 0x0000
    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010
    WM_QUIT = 0x0012
    WM_COMMAND = 0x0111
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    WM_CONTEXTMENU = 0x007B

    WM_APP = 0x8000
    WM_TRAY = WM_APP + 1

    NIM_ADD = 0
    NIM_DELETE = 2
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004

    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    LR_DEFAULTSIZE = 0x00000040
    IDI_APPLICATION = 32512

    MF_STRING = 0x00000000
    MF_SEPARATOR = 0x00000800
    TPM_RIGHTBUTTON = 0x0002

    ID_OPEN = 1001
    ID_QUIT = 1002

    ERROR_CLASS_ALREADY_EXISTS = 1410

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", wintypes.BYTE * 8),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("hWnd", wintypes.HWND),
            ("uID", wintypes.UINT),
            ("uFlags", wintypes.UINT),
            ("uCallbackMessage", wintypes.UINT),
            ("hIcon", wintypes.HICON),
            ("szTip", wintypes.WCHAR * 128),
            ("dwState", wintypes.DWORD),
            ("dwStateMask", wintypes.DWORD),
            ("szInfo", wintypes.WCHAR * 256),
            ("uTimeoutOrVersion", wintypes.UINT),
            ("szInfoTitle", wintypes.WCHAR * 64),
            ("dwInfoFlags", wintypes.DWORD),
            ("guidItem", GUID),
            ("hBalloonIcon", wintypes.HICON),
        ]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    user32.RegisterClassW.restype = ctypes.c_ushort
    user32.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
    user32.UnregisterClassW.restype = wintypes.BOOL
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    user32.DefWindowProcW.restype = LRESULT
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
    ]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = LRESULT
    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None
    user32.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterWindowMessageW.restype = wintypes.UINT
    user32.CreatePopupMenu.argtypes = []
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.DestroyMenu.restype = wintypes.BOOL
    user32.AppendMenuW.argtypes = [
        wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR
    ]
    user32.AppendMenuW.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.TrackPopupMenu.argtypes = [
        wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.LPVOID,
    ]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.LoadIconW.restype = wintypes.HICON
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.DestroyIcon.restype = wintypes.BOOL

    shell32.Shell_NotifyIconW.argtypes = [
        wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)
    ]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    shell32.ExtractIconW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT
    ]
    shell32.ExtractIconW.restype = wintypes.HICON

    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    CLASS_NAME = "FinVaultTrayWindow"

    def _load_icon():
        """Return (hicon, owned). Prefer the bundled .ico, then the EXE icon."""
        for folder in (RESOURCE_DIR, APP_DIR):
            path = Path(folder) / "assets" / "FinVault.ico"
            if path.is_file():
                handle = user32.LoadImageW(
                    None, str(path), IMAGE_ICON, 0, 0,
                    LR_LOADFROMFILE | LR_DEFAULTSIZE,
                )
                if handle:
                    return handle, True
        handle = shell32.ExtractIconW(None, sys.executable, 0)
        if handle and handle != 1:  # 1 means "no icons in this file"
            return handle, True
        handle = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        return handle, False

    class TrayIcon:
        """A tray icon plus its hidden window and message loop."""

        def __init__(
            self,
            url: str,
            on_open: Callable[[], None] | None = None,
            on_quit: Callable[[], None] | None = None,
        ) -> None:
            self.url = url
            self._on_open = on_open
            self._on_quit = on_quit
            self._thread: threading.Thread | None = None
            self._hwnd: int | None = None
            self._hicon: int | None = None
            self._icon_owned = False
            self._taskbar_msg = 0
            self._wndproc = None
            self._ready = threading.Event()
            self._stopping = threading.Event()

        # -- public API -----------------------------------------------------
        def start(self) -> bool:
            try:
                self._thread = threading.Thread(
                    target=self._run, name="finvault-tray", daemon=True
                )
                self._thread.start()
            except Exception:  # noqa: BLE001
                log.exception("Could not start the tray icon thread")
                return False
            self._ready.wait(3.0)
            return self._hwnd is not None

        def stop(self) -> None:
            self._stopping.set()
            self._ready.wait(1.0)
            self._close_window()
            thread = self._thread
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(3.0)

        # -- window plumbing -------------------------------------------------
        def _run(self) -> None:
            try:
                hinstance = kernel32.GetModuleHandleW(None)
                self._wndproc = WNDPROC(self._wnd_proc)
                wc = WNDCLASSW()
                wc.style = 0
                wc.lpfnWndProc = self._wndproc
                wc.cbClsExtra = 0
                wc.cbWndExtra = 0
                wc.hInstance = hinstance
                wc.hIcon = None
                wc.hCursor = None
                wc.hbrBackground = None
                wc.lpszMenuName = None
                wc.lpszClassName = CLASS_NAME
                if not user32.RegisterClassW(ctypes.byref(wc)):
                    error = ctypes.get_last_error()
                    if error != ERROR_CLASS_ALREADY_EXISTS:
                        log.warning("Tray: RegisterClassW failed (%s)", error)
                        return

                self._taskbar_msg = user32.RegisterWindowMessageW("TaskbarCreated")
                self._hwnd = user32.CreateWindowExW(
                    0, CLASS_NAME, "FinVault", 0, 0, 0, 0, 0,
                    None, None, hinstance, None,
                )
                if not self._hwnd:
                    log.warning(
                        "Tray: could not create the hidden window (%s)",
                        ctypes.get_last_error(),
                    )
                    return

                self._hicon, self._icon_owned = _load_icon()
                if not self._add_icon():
                    return
                self._ready.set()

                message = wintypes.MSG()
                while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                    user32.TranslateMessage(ctypes.byref(message))
                    user32.DispatchMessageW(ctypes.byref(message))
            except Exception:  # noqa: BLE001
                log.exception("Tray icon stopped unexpectedly")
            finally:
                self._ready.set()
                if self._hwnd:
                    try:
                        user32.DestroyWindow(self._hwnd)
                    except Exception:  # noqa: BLE001
                        pass
                    self._hwnd = None
                self._remove_icon()
                if self._hicon and self._icon_owned:
                    try:
                        user32.DestroyIcon(self._hicon)
                    except Exception:  # noqa: BLE001
                        pass
                self._hicon = None
                try:
                    user32.UnregisterClassW(CLASS_NAME, kernel32.GetModuleHandleW(None))
                except Exception:  # noqa: BLE001
                    pass

        def _wnd_proc(self, hwnd, msg, wparam, lparam):
            try:
                if msg == WM_TRAY:
                    event = lparam & 0xFFFF
                    if event == WM_LBUTTONDBLCLK:
                        self._open()
                    elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                        self._show_menu()
                    return 0
                if msg == self._taskbar_msg and self._taskbar_msg:
                    # Explorer restarted: the shell forgot every tray icon.
                    self._add_icon()
                    return 0
                if msg == WM_COMMAND:
                    command = wparam & 0xFFFF
                    if command == ID_OPEN:
                        self._open()
                    elif command == ID_QUIT:
                        self._quit()
                    return 0
                if msg == WM_CLOSE:
                    user32.DestroyWindow(hwnd)
                    return 0
                if msg == WM_DESTROY:
                    self._hwnd = None
                    self._remove_icon()
                    user32.PostQuitMessage(0)
                    return 0
            except Exception:  # noqa: BLE001 - never let an exception cross into Win32
                log.exception("Tray: window message failed")
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        def _show_menu(self) -> None:
            menu = user32.CreatePopupMenu()
            if not menu:
                return
            try:
                user32.AppendMenuW(menu, MF_STRING, ID_OPEN, "Open FinVault")
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
                user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "Quit FinVault")
                point = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(point))
                user32.SetForegroundWindow(self._hwnd)
                user32.TrackPopupMenu(
                    menu, TPM_RIGHTBUTTON, point.x, point.y, 0, self._hwnd, None
                )
                user32.PostMessageW(self._hwnd, WM_NULL, 0, 0)
            finally:
                user32.DestroyMenu(menu)

        # -- actions ----------------------------------------------------------
        def _open(self) -> None:
            if not self._on_open:
                return
            try:
                self._on_open()
            except Exception:  # noqa: BLE001
                log.exception("Tray: could not open the browser")

        def _quit(self) -> None:
            if self._stopping.is_set():
                return
            self._stopping.set()
            if self._on_quit:
                threading.Thread(
                    target=self._run_quit, name="finvault-tray-quit", daemon=True
                ).start()
            self._close_window()

        def _run_quit(self) -> None:
            try:
                self._on_quit()
            except Exception:  # noqa: BLE001
                log.exception("Tray: quit callback failed")

        def _close_window(self) -> None:
            hwnd = self._hwnd
            if hwnd:
                try:
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                except Exception:  # noqa: BLE001
                    pass

        # -- shell icon -------------------------------------------------------
        def _add_icon(self) -> bool:
            if not self._hwnd or not self._hicon:
                return False
            data = NOTIFYICONDATAW()
            data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            data.hWnd = self._hwnd
            data.uID = 1
            data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            data.uCallbackMessage = WM_TRAY
            data.hIcon = self._hicon
            data.szTip = TIP_TEXT
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
                log.warning(
                    "Tray: Shell_NotifyIcon(NIM_ADD) failed (%s)",
                    ctypes.get_last_error(),
                )
                return False
            return True

        def _remove_icon(self) -> None:
            if not self._hwnd:
                return
            data = NOTIFYICONDATAW()
            data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            data.hWnd = self._hwnd
            data.uID = 1
            try:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
            except Exception:  # noqa: BLE001
                pass

else:  # pragma: no cover - non-Windows fallback
    class TrayIcon:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Tray icons are only supported on Windows")
