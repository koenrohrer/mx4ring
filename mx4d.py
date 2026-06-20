#!/usr/bin/env python3
"""mx4ring daemon (GNOME front-end).

Owns the HID++ device and a session-bus service `dev.mx4ring.Daemon`:
  - signal OpenMenu(a(ss) items)  emitted when the menu button is pressed
  - signal CloseMenu()            emitted when it is released (extension commits)
  - method Buzz(s kind)           the extension calls for hover/select haptics

The GNOME Shell extension draws the radial menu at the cursor and selects on
release (press-hold-move-release). Remaps (keys/exec) are handled here directly.

    python mx4d.py        # Ctrl-C / SIGTERM un-diverts the buttons and exits
"""

import signal
import subprocess
import sys
import time

from gi.repository import Gio, GLib

import config_loader
config = config_loader.load()   # ensure config.py exists (from example), then import it
import haptic
from controls import ReprogControls
from hidpp import HidppError, open_device

BUS_NAME = "dev.mx4ring.Daemon"
OBJ_PATH = "/dev/mx4ring/Daemon"
IFACE_XML = """
<node>
  <interface name='dev.mx4ring.Daemon'>
    <signal name='OpenMenu'>
      <arg type='a(ssa(ss))' name='items'/>
    </signal>
    <signal name='CloseMenu'/>
    <method name='Buzz'>
      <arg type='s' name='kind' direction='in'/>
    </method>
  </interface>
</node>
"""

HAPTIC_FOR = {
    "open": config.HAPTIC_ON_OPEN,
    "hover": config.HAPTIC_ON_HOVER,
    "select": config.HAPTIC_ON_SELECT,
}


def collect_key_names():
    names = set()
    for kind, payload in config.REMAPS.values():
        if kind == "keys":
            names.update(payload)
    return names


def build_menu_items(menu):
    """Convert config menu entries into D-Bus (label, command, children) tuples.

    A leaf is ``(label, "shell command")``; a submenu is ``(label, [(label,
    command), ...])``.  Submenus carry their children; their own command is "".
    """
    out = []
    for label, payload in menu:
        if isinstance(payload, str):
            out.append((label, payload, []))
        else:
            out.append((label, "", [(cl, cc) for cl, cc in payload]))
    return out


def open_device_waiting(vid, timeout=30.0, interval=0.3):
    """Open the device, retrying while the mouse is asleep.

    The MX Master 4 powers its radio down when idle, so a fresh HID++ ping can
    fail even when it's connected on the Bolt channel. We use a short ping
    timeout so each sweep is fast (a few seconds, not ~20s) and loop for
    `timeout` seconds -- the instant a wiggle wakes the mouse, a sweep catches
    it. The live node answers in milliseconds, so the short timeout is safe.
    """
    print("Connecting to the mouse (move it to wake it if nothing happens)...")
    deadline = time.monotonic() + timeout
    while True:
        try:
            return open_device(vid, ping_timeout=0.1)
        except HidppError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(interval)


class Daemon:
    def __init__(self, loop):
        self.loop = loop
        self.conn = None
        self.owner_id = None
        self._cleaned = False
        self.held = set()

        self.dev = open_device_waiting(config.LOGITECH_VID)
        self.rc = ReprogControls.open(self.dev)

        self.remapper = None
        names = collect_key_names()
        if names:
            from uinput_remap import Remapper
            self.remapper = Remapper(names)

        self.diverted = []
        if config.MENU_BUTTON_CID is not None:
            self.rc.set_divert(config.MENU_BUTTON_CID, True)
            self.diverted.append(config.MENU_BUTTON_CID)
        for cid in config.REMAPS:
            self.rc.set_divert(cid, True)
            self.diverted.append(cid)

        self.node = Gio.DBusNodeInfo.new_for_xml(IFACE_XML)
        self.owner_id = Gio.bus_own_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
            self._on_bus_acquired, None, None)

        GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, self.dev.fileno(),
                              GLib.IOCondition.IN, self.on_hidraw)
        print(f"mx4ring daemon running. Diverted: {[hex(c) for c in self.diverted]} (Ctrl-C to stop)")

    # --- D-Bus -------------------------------------------------------------
    def _on_bus_acquired(self, conn, _name):
        self.conn = conn
        conn.register_object(OBJ_PATH, self.node.interfaces[0],
                             self._on_method_call, None, None)

    def _on_method_call(self, _conn, _sender, _path, _iface, method, params, invocation):
        if method == "Buzz":
            (kind,) = params.unpack()
            self.buzz(kind)
            invocation.return_value(None)
        else:
            invocation.return_dbus_error("org.freedesktop.DBus.Error.UnknownMethod", method)

    def emit(self, signal_name, variant=None):
        if self.conn is not None:
            self.conn.emit_signal(None, OBJ_PATH, BUS_NAME, signal_name, variant)

    # --- haptics -----------------------------------------------------------
    def buzz(self, kind):
        wf = HAPTIC_FOR.get(kind)
        if wf is not None:
            haptic.play(self.dev, wf)

    # --- HID++ events ------------------------------------------------------
    def on_hidraw(self, _fd, _cond, *_user):
        try:
            while True:
                ev = self.dev.read_event(timeout=0.0)   # drain everything ready
                if not ev:
                    break
                cids = self.rc.parse_event(*ev)
                if cids is None:
                    continue
                for cid in cids - self.held:             # newly pressed
                    self.on_press(cid)
                for cid in self.held - cids:             # newly released
                    self.on_release(cid)
                self.held = cids
        except OSError as exc:
            print(f"device read error: {exc}; stopping")
            self.cleanup()
            self.loop.quit()
            return False
        return True

    def on_press(self, cid):
        if cid == config.MENU_BUTTON_CID:
            self.buzz("open")
            items = build_menu_items(config.MENUS.get("default", []))
            self.emit("OpenMenu", GLib.Variant("(a(ssa(ss)))", (items,)))
        elif cid in config.REMAPS:
            kind, payload = config.REMAPS[cid]
            if kind == "keys" and self.remapper:
                self.remapper.tap(payload)
            elif kind == "exec":
                subprocess.Popen(["sh", "-c", payload])

    def on_release(self, cid):
        if cid == config.MENU_BUTTON_CID:
            self.emit("CloseMenu", None)

    def cleanup(self):
        if self._cleaned:
            return
        self._cleaned = True
        for cid in self.diverted:
            try:
                self.rc.set_divert(cid, False)
            except Exception:
                pass
        if self.remapper:
            self.remapper.close()
        if self.owner_id:
            Gio.bus_unown_name(self.owner_id)


def main():
    try:
        config_loader.validate(config)
    except config_loader.ConfigError as exc:
        sys.exit(f"config.py problem: {exc}")

    if config.MENU_BUTTON_CID is None and not config.REMAPS:
        sys.exit("Nothing configured. Set MENU_BUTTON_CID/REMAPS in config.py "
                 "(use `python discover.py --watch` to find CIDs).")

    loop = GLib.MainLoop()
    try:
        daemon = Daemon(loop)
    except HidppError as exc:
        sys.exit(str(exc))

    def on_signal(*_user):
        daemon.cleanup()
        loop.quit()
        return GLib.SOURCE_REMOVE

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, on_signal)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, on_signal)
    try:
        loop.run()
    finally:
        daemon.cleanup()


if __name__ == "__main__":
    main()
