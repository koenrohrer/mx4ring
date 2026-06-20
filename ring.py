#!/usr/bin/env python3
"""The radial menu overlay, as a reusable window owned by the daemon process.

RingWindow is created once and shown/hidden on demand (no per-press process
launch). `haptic_cb(kind)` is called with "open" / "hover" / "select" so the
daemon -- the sole owner of the HID++ device -- can fire the motor.

Run standalone (`python ring.py [menu]`) to test the UI with no device/haptics.
"""

import math
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as LayerShell
    HAVE_LAYER = True
except (ValueError, ImportError):
    HAVE_LAYER = False

HOVER_THROTTLE = 0.04   # seconds between hover "detent" buzzes


def _layer_supported():
    """The library can import yet the *compositor* may not support the protocol
    (e.g. GNOME/Mutter). is_supported() is the real runtime check; fall back to
    a desktop sniff on older library versions that lack it."""
    if not HAVE_LAYER:
        return False
    try:
        return LayerShell.is_supported()
    except Exception:
        import os
        return "gnome" not in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


class RingWindow(Gtk.ApplicationWindow):
    def __init__(self, app, haptic_cb=None):
        super().__init__(application=app)
        self.haptic_cb = haptic_cb or (lambda kind: None)
        self.items = []
        self.selected = -1
        self.cx = self.cy = 0
        self._last_hover = 0.0
        self.set_decorated(False)

        if _layer_supported():
            LayerShell.init_for_window(self)
            LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
            LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.EXCLUSIVE)
            for edge in (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM,
                         LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT):
                LayerShell.set_anchor(self, edge, True)
        else:
            self.fullscreen()

        area = Gtk.DrawingArea()
        area.set_draw_func(self.draw)
        self.set_child(area)
        self.area = area

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.on_motion)
        area.add_controller(motion)

        click = Gtk.GestureClick()
        click.connect("pressed", self.on_click)
        area.add_controller(click)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        self.add_controller(keys)

    # --- show / hide -------------------------------------------------------
    def show_menu(self, items):
        self.items = items
        self.selected = -1
        self.set_visible(True)        # maps the surface -> grabs keyboard
        self.area.queue_draw()
        self.haptic_cb("open")

    def hide_menu(self):
        self.set_visible(False)       # unmaps -> releases keyboard to other apps

    # --- drawing -----------------------------------------------------------
    def draw(self, _area, cr, w, h):
        self.cx, self.cy = w / 2, h / 2
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.paint()
        radius = min(w, h) * 0.28
        n = max(len(self.items), 1)
        cr.select_font_face("Sans")
        cr.set_font_size(18)
        for i, (label, _) in enumerate(self.items):
            ang = -math.pi / 2 + 2 * math.pi * i / n
            x = self.cx + radius * math.cos(ang)
            y = self.cy + radius * math.sin(ang)
            if i == self.selected:
                cr.set_source_rgba(0.20, 0.55, 0.95, 0.95)
            else:
                cr.set_source_rgba(0.15, 0.15, 0.17, 0.92)
            cr.arc(x, y, 48, 0, 2 * math.pi)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 1)
            ext = cr.text_extents(label)
            cr.move_to(x - ext.width / 2, y + ext.height / 2)
            cr.show_text(label)
        cr.set_source_rgba(1, 1, 1, 0.85)
        cr.arc(self.cx, self.cy, 6, 0, 2 * math.pi)
        cr.fill()

    def index_for(self, x, y):
        dx, dy = x - self.cx, y - self.cy
        if math.hypot(dx, dy) < 40:           # center dead zone
            return -1
        ang = math.atan2(dy, dx) + math.pi / 2
        if ang < 0:
            ang += 2 * math.pi
        n = len(self.items)
        return int((ang + math.pi / n) % (2 * math.pi) / (2 * math.pi) * n) % n

    # --- input -------------------------------------------------------------
    def on_motion(self, _ctrl, x, y):
        idx = self.index_for(x, y)
        if idx != self.selected:
            self.selected = idx
            self.area.queue_draw()
            if idx >= 0:
                now = time.monotonic()
                if now - self._last_hover >= HOVER_THROTTLE:
                    self._last_hover = now
                    self.haptic_cb("hover")

    def on_click(self, _g, _n, x, y):
        self.choose(self.index_for(x, y))

    def on_key(self, _c, keyval, _code, _state):
        if keyval == Gdk.KEY_Escape:
            self.hide_menu()
        return False

    def choose(self, idx):
        if 0 <= idx < len(self.items):
            self.haptic_cb("select")
            subprocess.Popen(["sh", "-c", self.items[idx][1]])
        self.hide_menu()


def main():
    """Standalone UI test (no device, no haptics)."""
    from config import MENUS
    name = sys.argv[1] if len(sys.argv) > 1 else "default"
    items = MENUS.get(name, MENUS["default"])
    app = Gtk.Application(application_id="dev.mx4ring.RingTest")
    app.connect("activate", lambda a: RingWindow(a).show_menu(items))
    app.run([])


if __name__ == "__main__":
    main()
