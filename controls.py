"""HID++ feature discovery + Reprogrammable Controls v4 (0x1b04).

This is the layer that lets you (a) see what the device supports and
(b) "divert" a button so it notifies us instead of doing its default thing.
"""

from hidpp import HidppError

FEATURE_FEATURE_SET = 0x0001
FEATURE_REPROG_CONTROLS_V4 = 0x1B04

# cidInfo flag bits (low byte) -- same numbering Solaar/libratbag use
FLAG_DIVERTABLE = 0x20
FLAG_PERSIST_DIVERTABLE = 0x40


def get_feature_index(dev, feature_id):
    """Resolve a 16-bit feature id to its per-device index (0 = unsupported)."""
    p = dev.request(0x00, 0x00, bytes([(feature_id >> 8) & 0xFF, feature_id & 0xFF, 0]))
    return p[0]


def list_features(dev):
    """Return [(index, feature_id, version), ...] for the whole device."""
    fs = get_feature_index(dev, FEATURE_FEATURE_SET)
    out = [(0x00, 0x0000, 0)]
    if not fs:
        return out
    count = dev.request(fs, 0x00)[0]
    for i in range(1, count + 1):
        p = dev.request(fs, 0x01, bytes([i])).ljust(4, b"\x00")
        out.append((i, (p[0] << 8) | p[1], p[3]))
    return out


class Control:
    def __init__(self, index, cid, tid, flags, pos, group, gmask):
        self.index = index
        self.cid = cid
        self.tid = tid
        self.flags = flags
        self.pos = pos
        self.group = group
        self.gmask = gmask

    @property
    def divertable(self):
        return bool(self.flags & FLAG_DIVERTABLE)

    @property
    def persist_divertable(self):
        return bool(self.flags & FLAG_PERSIST_DIVERTABLE)


class ReprogControls:
    def __init__(self, dev, index):
        self.dev = dev
        self.index = index

    @classmethod
    def open(cls, dev):
        idx = get_feature_index(dev, FEATURE_REPROG_CONTROLS_V4)
        if not idx:
            raise HidppError("device has no Reprogrammable Controls v4 (0x1b04)")
        return cls(dev, idx)

    def count(self):
        return self.dev.request(self.index, 0x00)[0]

    def control(self, i):
        p = self.dev.request(self.index, 0x01, bytes([i])).ljust(8, b"\x00")
        return Control(i, (p[0] << 8) | p[1], (p[2] << 8) | p[3], p[4], p[5], p[6], p[7])

    def controls(self):
        return [self.control(i) for i in range(self.count())]

    def set_divert(self, cid, on=True):
        """Set/clear the divert bit. bfield: bit0 value, bit1 'value is valid'."""
        bfield = 0x03 if on else 0x02
        self.dev.request(self.index, 0x03,
                         bytes([(cid >> 8) & 0xFF, cid & 0xFF, bfield, 0, 0]))

    def parse_event(self, feature_index, addr, params):
        """If this report is a divertedButtons event, return the set of held CIDs."""
        if feature_index != self.index or addr != 0x00:
            return None
        params = bytes(params).ljust(8, b"\x00")
        held = set()
        for off in (0, 2, 4, 6):
            cid = (params[off] << 8) | params[off + 1]
            if cid:
                held.add(cid)
        return held
