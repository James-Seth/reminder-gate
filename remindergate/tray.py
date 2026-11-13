"""
System-tray icon via pystray.

Menu: Unlock now (opens the prompt) | Settings | History | Quit
Icon is generated at runtime with Pillow (no .ico file needed).
"""

import threading
import logging
import sys
from pathlib import Path

from PIL import Image
import pystray
from pystray._base import Icon as BaseIcon

from remindergate import __app_name__

log = logging.getLogger(__name__)


def _load_icon() -> Image.Image:
    app_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    icon_path = app_dir / "screenshots" / "tray-icon.png"
    with Image.open(icon_path) as icon:
        return icon.convert("RGBA")


class TrayIcon:

    def __init__(self, on_unlock, on_settings, on_history, on_quit):
        self._on_unlock = on_unlock
        self._on_settings = on_settings
        self._on_history = on_history
        self._on_quit = on_quit
        self._icon: BaseIcon | None = None

    def start(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Unlock now", self._on_unlock),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", self._on_settings),
            pystray.MenuItem("History", self._on_history),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(__app_name__, _load_icon(), __app_name__, menu)
        threading.Thread(target=self._icon.run, daemon=True).start()
        log.info("Tray started")

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def notify(self, message: str) -> None:
        if self._icon:
            self._icon.notify(message, __app_name__)
