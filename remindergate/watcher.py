"""
Steam window watcher.

reminder-gate never kills the Steam process, so Steam can keep running in the
background (tray only) and download updates. It only reacts when the user
*opens* the main Steam window while today is still locked: it closes that
window (Steam drops back to the tray, downloads keep going) and fires a
callback so the app can show the prompt.

Debug helper — list the windows reminder-gate can see:
    python -m remindergate.watcher
"""

import sys
import threading
import logging

log = logging.getLogger(__name__)

# What counts as "the Steam main window". The modern Steam client draws its
# main window through steamwebhelper.exe with the title "Steam". The
# bootstrapper/updater dialog belongs to steam.exe, so it's left alone.
STEAM_WINDOW_TITLE = "Steam"
STEAM_WINDOW_PROCESSES = {"steamwebhelper.exe"}
MIN_WIDTH, MIN_HEIGHT = 300, 200   # skip tiny helper/minimized windows


# ─── Win32 helpers (ctypes, no extra dependencies) ───────────────────

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _WM_CLOSE = 0x0010

    def _process_name(pid: int) -> str:
        h = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(buf))
            if _kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return buf.value.rsplit("\\", 1)[-1].lower()
            return ""
        finally:
            _kernel32.CloseHandle(h)

    def _visible_windows() -> list[tuple[int, str, str, int, int]]:
        """(hwnd, title, process_name, width, height) for visible top-level windows."""
        out = []
        names: dict[int, str] = {}

        def cb(hwnd, _lparam):
            if not _user32.IsWindowVisible(hwnd):
                return True
            n = _user32.GetWindowTextLengthW(hwnd)
            if n == 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            _user32.GetWindowTextW(hwnd, buf, n + 1)
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value not in names:
                names[pid.value] = _process_name(pid.value)
            r = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append((hwnd, buf.value, names[pid.value], r.right - r.left, r.bottom - r.top))
            return True

        _user32.EnumWindows(_EnumWindowsProc(cb), 0)
        return out

    def find_steam_windows() -> list[int]:
        return [
            hwnd for hwnd, title, proc, w, h in _visible_windows()
            if title == STEAM_WINDOW_TITLE
            and proc in STEAM_WINDOW_PROCESSES
            and w >= MIN_WIDTH and h >= MIN_HEIGHT
        ]

    def close_window(hwnd: int) -> None:
        """Ask the window to close. Steam hides to the tray; the process keeps running."""
        _user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)

else:  # non-Windows: lets the module import for tests / development
    def _visible_windows():
        return []

    def find_steam_windows() -> list[int]:
        return []

    def close_window(hwnd: int) -> None:
        pass


# ─── Watcher ─────────────────────────────────────────────────────────

class SteamWatcher:
    """Background thread that gates the Steam main window."""

    def __init__(self, is_unlocked_fn, on_blocked_fn, interval: float = 2.0,
                 find_fn=None, close_fn=None):
        """
        Args:
            is_unlocked_fn: callable() -> bool — is today unlocked?
            on_blocked_fn:  callable() — called (on the watcher thread) after
                            the Steam window was closed because today is locked.
            interval:       seconds between checks.
            find_fn/close_fn: overridable for testing.
        """
        self._is_unlocked = is_unlocked_fn
        self._on_blocked = on_blocked_fn
        self._interval = interval
        self._find = find_fn or find_steam_windows
        self._close = close_fn or close_window
        self._was_open = False  # False on start → a window already open gets gated
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Watcher started (interval=%ss)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Watcher stopped")

    def check_once(self) -> None:
        windows = self._find()
        is_open = bool(windows)
        # Only react when the window *opens*. A window that was already open
        # (e.g. you were using Steam when midnight passed) is left alone.
        if is_open and not self._was_open and not self._is_unlocked():
            log.info("Steam window opened while locked — closing to tray and prompting")
            for hwnd in windows:
                self._close(hwnd)
            is_open = False
            self._on_blocked()
        self._was_open = is_open

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.check_once()
            except Exception:
                log.exception("Watcher loop error")
            self._stop_event.wait(self._interval)


# ─── Debug: python -m remindergate.watcher ───────────────────────────

if __name__ == "__main__":
    if sys.platform != "win32":
        sys.exit("Windows only.")
    print(f"{'process':<24} {'size':>11}  title")
    for hwnd, title, proc, w, h in _visible_windows():
        mark = "  <-- Steam main window" if hwnd in find_steam_windows() else ""
        print(f"{proc:<24} {w:>5}x{h:<5}  {title}{mark}")
