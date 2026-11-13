"""
GUI windows — native Windows look via ttk.

  - GatePrompt       (the blocking "confirm to unlock" dialog)
  - SettingsWindow    (steam path, interval, prompt text, autostart)
  - HistoryWindow     (streak + recent log)

No health-specific language — the user sets their own prompt text.
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from remindergate import __app_name__, __version__
from remindergate import config


# ─── Gate prompt ────────────────────────────────────────────────────

class GatePrompt(tk.Toplevel):
    """Blocks Steam until the user ticks the checkbox and confirms."""

    def __init__(self, prompt_text: str, on_confirm, on_dismiss=None):
        super().__init__()
        self.title(__app_name__)
        self.geometry("340x150")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.protocol("WM_DELETE_WINDOW", self._dismiss)

        self._on_confirm = on_confirm
        self._on_dismiss = on_dismiss

        # Centre on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 340) // 2
        y = (self.winfo_screenheight() - 150) // 2
        self.geometry(f"+{x}+{y}")

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame, text="Steam is locked for today.", font=("", 11, "bold"),
        ).pack(anchor="w")

        self._var = tk.BooleanVar()
        self._cb = ttk.Checkbutton(
            frame, text=prompt_text, variable=self._var, command=self._toggle,
        )
        self._cb.pack(anchor="w", pady=(10, 10))

        btn_row = ttk.Frame(frame)
        btn_row.pack(anchor="w")

        self._ok = ttk.Button(btn_row, text="Confirm", state="disabled", command=self._confirm)
        self._ok.pack(side="left", padx=(0, 6))
        ttk.Button(btn_row, text="Not now", command=self._dismiss).pack(side="left")

        self.grab_set()
        self.focus_force()

    def _toggle(self):
        self._ok.state(["!disabled"] if self._var.get() else ["disabled"])

    def _confirm(self):
        self.destroy()
        if self._on_confirm:
            self._on_confirm()

    def _dismiss(self):
        self.destroy()
        if self._on_dismiss:
            self._on_dismiss()


# ─── Settings window ────────────────────────────────────────────────

class SettingsWindow(tk.Toplevel):

    def __init__(self, cfg: dict, on_save=None):
        super().__init__()
        self.title(f"{__app_name__} — Settings")
        self.geometry("440x280")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self._cfg = cfg
        self._on_save = on_save

        self.update_idletasks()
        x = (self.winfo_screenwidth() - 440) // 2
        y = (self.winfo_screenheight() - 280) // 2
        self.geometry(f"+{x}+{y}")

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        # Steam path
        ttk.Label(frame, text="Steam.exe path:").pack(anchor="w")
        path_row = ttk.Frame(frame)
        path_row.pack(fill="x", pady=(2, 8))

        self._path_var = tk.StringVar(value=cfg.get("steam_path", ""))
        ttk.Entry(path_row, textvariable=self._path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="Browse…", command=self._browse).pack(side="right", padx=(6, 0))

        # Prompt text
        ttk.Label(frame, text="Checkbox label (set your own reminder):").pack(anchor="w")
        self._prompt_var = tk.StringVar(value=cfg.get("prompt_text", config.DEFAULT_PROMPT))
        ttk.Entry(frame, textvariable=self._prompt_var).pack(fill="x", pady=(2, 8))

        # Check interval
        interval_row = ttk.Frame(frame)
        interval_row.pack(anchor="w", pady=(0, 8))
        ttk.Label(interval_row, text="Check interval (seconds):").pack(side="left")
        self._interval_var = tk.IntVar(value=cfg.get("check_interval_seconds", 2))
        ttk.Spinbox(interval_row, from_=1, to=30, textvariable=self._interval_var, width=5).pack(side="left", padx=(6, 0))

        # Autostart
        self._autostart_var = tk.BooleanVar(value=cfg.get("start_with_windows", False))
        ttk.Checkbutton(frame, text="Start with Windows", variable=self._autostart_var).pack(anchor="w", pady=(0, 12))

        # Save
        ttk.Button(frame, text="Save", command=self._save).pack(anchor="w")

    def _browse(self):
        p = filedialog.askopenfilename(
            title="Locate Steam.exe",
            filetypes=[("Executable", "*.exe")],
            initialdir=r"C:\Program Files (x86)\Steam",
        )
        if p:
            self._path_var.set(p)

    def _save(self):
        self._cfg["steam_path"] = self._path_var.get()
        self._cfg["prompt_text"] = self._prompt_var.get().strip() or config.DEFAULT_PROMPT
        try:
            interval = int(self._interval_var.get())
        except (tk.TclError, ValueError):
            interval = 2
        self._cfg["check_interval_seconds"] = max(1, min(30, interval))
        self._cfg["start_with_windows"] = self._autostart_var.get()
        config.save(self._cfg)
        if _setup_autostart(self._autostart_var.get()):
            messagebox.showinfo(__app_name__, "Settings saved.", parent=self)
        else:
            messagebox.showwarning(
                __app_name__,
                "Settings saved, but the Start with Windows setting couldn't be changed.\n"
                "You can add a shortcut to shell:startup manually instead.",
                parent=self,
            )
        if self._on_save:
            self._on_save(self._cfg)
        self.destroy()


# ─── History / streak window ────────────────────────────────────────

class HistoryWindow(tk.Toplevel):

    def __init__(self, cfg: dict):
        super().__init__()
        self.title(f"{__app_name__} — History")
        self.geometry("320x360")
        self.resizable(False, False)
        self.attributes("-topmost", True)

        self.update_idletasks()
        x = (self.winfo_screenwidth() - 320) // 2
        y = (self.winfo_screenheight() - 360) // 2
        self.geometry(f"+{x}+{y}")

        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        streak = config.get_streak(cfg)
        today_done = config.is_unlocked_today(cfg)

        ttk.Label(frame, text=f"{streak}-day streak", font=("", 14, "bold")).pack(anchor="w")
        status = "Confirmed today" if today_done else "Not yet confirmed today"
        ttk.Label(frame, text=status).pack(anchor="w", pady=(0, 8))

        ttk.Separator(frame).pack(fill="x", pady=4)

        ttk.Label(frame, text="Recent confirmations", font=("", 10, "bold")).pack(anchor="w", pady=(4, 4))

        history = config.get_history(cfg, limit=30)
        if not history:
            ttk.Label(frame, text="No history yet.").pack(anchor="w", pady=8)
        else:
            list_frame = ttk.Frame(frame)
            list_frame.pack(fill="both", expand=True)

            scrollbar = ttk.Scrollbar(list_frame)
            scrollbar.pack(side="right", fill="y")

            listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Consolas", 9))
            for entry in history:
                listbox.insert("end", f"  {entry['date']}   {entry['time']}")
            listbox.pack(fill="both", expand=True)
            scrollbar.config(command=listbox.yview)


# ─── Autostart helper ───────────────────────────────────────────────

def _setup_autostart(enable: bool) -> bool:
    """Add/remove the HKCU Run entry. Returns False if it failed."""
    try:
        import winreg
    except ImportError:
        return not enable
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            import sys
            exe = sys.executable
            if getattr(sys, "frozen", False):
                cmd = f'"{exe}"'
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "run_remindergate.pyw")
                cmd = f'"{exe}" "{script}"'
            winreg.SetValueEx(key, __app_name__, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, __app_name__)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False
