"""Emit remapped key chords through a kernel uinput virtual keyboard.

uinput lives below the display server, so this works on Wayland *and* X11 --
unlike trying to synthesize keystrokes into the compositor directly.

Needs write access to /dev/uinput (see README for the udev rule).
"""

from evdev import UInput, ecodes


class Remapper:
    def __init__(self, key_names):
        codes = sorted({getattr(ecodes, n) for n in key_names})
        self.ui = UInput({ecodes.EV_KEY: codes}, name="mx4ring-virtual-kbd")

    def tap(self, key_names):
        codes = [getattr(ecodes, n) for n in key_names]
        for c in codes:
            self.ui.write(ecodes.EV_KEY, c, 1)
        self.ui.syn()
        for c in reversed(codes):
            self.ui.write(ecodes.EV_KEY, c, 0)
        self.ui.syn()

    def close(self):
        self.ui.close()
