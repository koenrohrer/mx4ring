"""Best-effort haptic motor control for the MX Master 4.

Reverse-engineered (see lukasfri/mx4notifications). The waveform-play command
is a SHORT report whose bytes 2-3 are the 16-bit word below and whose first
data byte is the waveform index (0-14):

    0x0B4E = (feature_index 0x0B << 8) | addr 0x4E   # addr 0x4E = function 4, swid 14

The feature *index* (0x0B) is firmware-specific. If you don't feel a buzz,
run `python discover.py`, find the haptic feature in the printed table, and
update the high byte of HAPTIC_WORD to its index.
"""

HAPTIC_WORD = 0x0B4E


def play(dev, waveform):
    feature_index = HAPTIC_WORD >> 8
    addr = HAPTIC_WORD & 0xFF
    try:
        dev.write_raw(feature_index, addr, bytes([waveform & 0xFF, 0, 0]))
    except Exception as exc:                 # haptics are non-essential
        print(f"[haptic] failed: {exc}")
