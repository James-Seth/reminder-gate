"""
System-tray icon via pystray.

Menu: Unlock now (opens the prompt) | Settings | History | Quit
Icon is generated at runtime with Pillow (no .ico file needed).
"""

import threading
import logging

from PIL import Image, ImageDraw
import pystray

from remindergate import __app_name__

log = logging.getLogger(__name__)


def _make_icon(size: int = 64) -> Image.Image:
    """Simple gate/lock icon — a padlock silhouette."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size // 8  # margin

    # Shackle (arc)
    shackle_box = [m + 8, m, size - m - 8, size // 2 + 4]
    d.arc(shackle_box, 180, 360, fill="#4a7abc", width=4)

    # Body (rounded rect approximation)
    body = [m, size // 3, size - m, size - m]
    d.rounded_rectangle(body, radius=4, fill="#4a7abc")

    # Keyhole
    cx, cy = size // 2, int(size * 0.52)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill="white")
    d.polygon([(cx - 3, cy + 2), (cx + 3, cy + 2), (cx, cy + 12)], fill="white")

    return img


class TrayIcon:

    def __init__(self, on_unlock, on_settings, on_history, on_quit):
        self._on_unlock = on_unlock
        self._on_settings = on_settings
        self._on_history = on_history
        self._on_quit = on_quit
        self._icon: pystray.Icon | None = None

    def start(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("Unlock now", self._on_unlock),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", self._on_settings),
            pystray.MenuItem("History", self._on_history),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(__app_name__, _make_icon(), __app_name__, menu)
        threading.Thread(target=self._icon.run, daemon=True).start()
        log.info("Tray started")

    def stop(self) -> None:
        if self._icon:
            self._icon.stop()

    def notify(self, message: str) -> None:
        if self._icon:
            self._icon.notify(message, __app_name__)
