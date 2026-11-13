"""
reminder-gate — entry point.

.pyw extension = no console window on Windows.
"""

import sys
import os
import queue
import logging
import subprocess
import tkinter as tk
from logging.handlers import RotatingFileHandler

from remindergate.config import _data_dir

_handler = RotatingFileHandler(
    str(_data_dir() / "remindergate.log"), maxBytes=1_000_000, backupCount=3, encoding="utf-8",
)
_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_handler])
log = logging.getLogger("remindergate")

# ─── Single-instance guard ──────────────────────────────────────────

_LOCK = _data_dir() / "remindergate.lock"


def _acquire_lock() -> bool:
    if _LOCK.exists():
        try:
            old_pid = int(_LOCK.read_text().strip())
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {old_pid}", "/NH"],
                capture_output=True, text=True, creationflags=0x08000000,
            )
            if str(old_pid) in out.stdout:
                return False
        except Exception:
            pass
    _LOCK.write_text(str(os.getpid()))
    return True


def _release_lock():
    try:
        _LOCK.unlink(missing_ok=True)
    except Exception:
        pass


# ─── App ────────────────────────────────────────────────────────────

from remindergate import config
from remindergate.watcher import SteamWatcher
from remindergate.tray import TrayIcon
from remindergate.ui import GatePrompt, SettingsWindow, HistoryWindow


class ReminderGateApp:

    def __init__(self):
        self.cfg = config.load()
        self.root = tk.Tk()
        self.root.withdraw()

        # Tkinter may only be touched from the main thread. The watcher and the
        # tray run on their own threads, so they drop work into this queue and
        # the main loop picks it up.
        self._calls: queue.Queue = queue.Queue()
        self._windows: dict[str, tk.Toplevel] = {}

        self.watcher = self._make_watcher()

        self.tray = TrayIcon(
            on_unlock=lambda *_: self._call_soon(self._unlock_from_tray),
            on_settings=lambda *_: self._call_soon(self._show_settings),
            on_history=lambda *_: self._call_soon(self._show_history),
            on_quit=lambda *_: self._call_soon(self._quit),
        )

    # ── threading helpers ──

    def _call_soon(self, fn) -> None:
        self._calls.put(fn)

    def _pump(self) -> None:
        while True:
            try:
                fn = self._calls.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log.exception("UI callback error")
        self.root.after(100, self._pump)

    def _single(self, key: str, factory) -> None:
        """Open a window, or bring it forward if it's already open."""
        win = self._windows.get(key)
        if win is not None and win.winfo_exists():
            win.deiconify()
            win.lift()
            win.focus_force()
            return
        self._windows[key] = factory()

    # ── lifecycle ──

    def _make_watcher(self) -> SteamWatcher:
        return SteamWatcher(
            is_unlocked_fn=lambda: config.is_unlocked_today(self.cfg),
            on_blocked_fn=lambda: self._call_soon(self._show_prompt),
            interval=self.cfg.get("check_interval_seconds", 2),
        )

    def run(self) -> None:
        log.info("reminder-gate starting")
        self.tray.start()
        self.watcher.start()
        self.root.after(100, self._pump)
        self.root.mainloop()

    def _quit(self) -> None:
        log.info("reminder-gate quitting")
        self.watcher.stop()
        self.tray.stop()
        _release_lock()
        self.root.quit()

    # ── prompt ──

    def _unlock_from_tray(self) -> None:
        if config.is_unlocked_today(self.cfg):
            self.tray.notify("Already confirmed today.")
            return
        self._show_prompt()

    def _show_prompt(self) -> None:
        prompt_text = self.cfg.get("prompt_text", config.DEFAULT_PROMPT)

        def on_confirm():
            self.cfg = config.unlock_today(self.cfg)
            log.info("Unlocked for today")
            self._open_steam()

        self._single("prompt", lambda: GatePrompt(prompt_text, on_confirm=on_confirm))

    def _open_steam(self) -> None:
        """Bring the Steam window back (Steam is usually still running in the tray)."""
        if hasattr(os, "startfile"):
            try:
                os.startfile("steam://open/main")
                self.tray.notify("Unlocked! Opening Steam.")
                return
            except OSError:
                log.warning("steam:// protocol not available, falling back to Steam.exe")
        steam = self.cfg.get("steam_path", "")
        if steam and os.path.isfile(steam):
            subprocess.Popen([steam])
            self.tray.notify("Unlocked! Opening Steam.")
        else:
            self.tray.notify("Unlocked, but Steam wasn't found. Check the path in Settings.")

    # ── other windows ──

    def _show_settings(self) -> None:
        def on_save(new_cfg):
            self.cfg = new_cfg
            self.watcher.stop()
            self.watcher = self._make_watcher()
            self.watcher.start()

        self._single("settings", lambda: SettingsWindow(self.cfg, on_save=on_save))

    def _show_history(self) -> None:
        self._single("history", lambda: HistoryWindow(self.cfg))


# ─── Main ───────────────────────────────────────────────────────────

def main():
    if not _acquire_lock():
        r = tk.Tk()
        r.withdraw()
        from tkinter import messagebox
        messagebox.showinfo("reminder-gate", "reminder-gate is already running.\nCheck your system tray.")
        sys.exit(0)
    try:
        app = ReminderGateApp()
        app.run()
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
