"""
Configuration and history manager.

Stores settings in a JSON file under %APPDATA%/reminder-gate/.
No personal or health data is stored — just dates/times of confirmations.
"""

import copy
import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path


def _data_dir() -> Path:
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    d = Path(base) / "reminder-gate"
    d.mkdir(parents=True, exist_ok=True)
    return d


CONFIG_PATH = _data_dir() / "config.json"

DEFAULT_PROMPT = "I completed my daily check"

_DEFAULTS = {
    "steam_path": r"C:\Program Files (x86)\Steam\Steam.exe",
    "check_interval_seconds": 2,
    "start_with_windows": False,
    "prompt_text": DEFAULT_PROMPT,   # user can customise this
    "history": [],          # list of {"date": "YYYY-MM-DD", "time": "HH:MM:SS"}
    "unlock_date": None,
}


def load() -> dict:
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                raise ValueError("config is not a JSON object")
        except (json.JSONDecodeError, ValueError, OSError):
            # Keep the broken file so history isn't silently lost.
            try:
                os.replace(CONFIG_PATH, CONFIG_PATH.with_name("config.json.bad"))
            except OSError:
                pass
            cfg = {}
    for k, v in _DEFAULTS.items():
        cfg.setdefault(k, copy.deepcopy(v))
    return cfg


def save(cfg: dict) -> None:
    """Write atomically: a crash mid-save can't leave a half-written file."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, CONFIG_PATH)


def is_unlocked_today(cfg: dict) -> bool:
    return cfg.get("unlock_date") == date.today().isoformat()


def unlock_today(cfg: dict) -> dict:
    if is_unlocked_today(cfg):
        return cfg  # don't log the same day twice
    today = date.today().isoformat()
    now = datetime.now().strftime("%H:%M:%S")
    cfg["unlock_date"] = today
    cfg.setdefault("history", []).append({"date": today, "time": now})
    save(cfg)
    return cfg


def get_streak(cfg: dict) -> int:
    """Consecutive confirmed days ending today — or yesterday, if today
    isn't confirmed yet (the streak is still alive until midnight)."""
    dates = {e["date"] for e in cfg.get("history", []) if "date" in e}
    if not dates:
        return 0
    expected = date.today()
    if expected.isoformat() not in dates:
        expected -= timedelta(days=1)
    streak = 0
    while expected.isoformat() in dates:
        streak += 1
        expected -= timedelta(days=1)
    return streak


def get_history(cfg: dict, limit: int = 30) -> list[dict]:
    return list(reversed(cfg.get("history", [])))[:limit]
