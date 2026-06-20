"""Minimal HID++ 2.0 transport for Logitech devices over a Bolt receiver.

I/O is done on a raw hidraw file descriptor (os.read/os.write) so the fd can be
watched by GLib's main loop. The `hid` package is used only to *locate* the
receiver's HID++ interface (its hidraw path + usage page).

Report layout (first byte is the HID report id):
    short (7 bytes):   10  devidx  featidx  addr  p0 p1 p2
    long  (20 bytes):  11  devidx  featidx  addr  p0 .. p15
    addr = (function << 4) | software_id   (your requests: nonzero swid; events: swid 0)
"""

import os
import select

import hid

SHORT_ID, LONG_ID = 0x10, 0x11
HIDPP_USAGE_PAGE = 0xFF00


class HidppError(Exception):
    pass


def _packet(device_index, feature_index, addr, data):
    if len(data) <= 3:
        return bytes([SHORT_ID, device_index, feature_index, addr]) + data.ljust(3, b"\x00")
    return bytes([LONG_ID, device_index, feature_index, addr]) + data.ljust(16, b"\x00")


def _read(fd, timeout_s):
    r, _, _ = select.select([fd], [], [], timeout_s)
    if not r:
        return None
    return os.read(fd, 64)            # a report is 7 or 20 bytes; 64 is safe


def _ping(fd, device_index, swid=0x0F, mark=0x5A, read_timeout=0.4):
    """root.getProtocolVersion echoes `mark` -> proves this index is alive."""
    os.write(fd, _packet(device_index, 0x00, (0x01 << 4) | swid, bytes([0, 0, mark])))
    for _ in range(6):
        resp = _read(fd, read_timeout)
        if not resp:
            return False
        if resp[1] == device_index and resp[2] == 0xFF:      # error => no such device
            return False
        if resp[1] == device_index and resp[2] == 0x00 and (resp[3] & 0x0F) == swid:
            return len(resp) >= 7 and resp[6] == mark
    return False


def open_device(vid=0x046D, ping_timeout=0.4):
    """Find the receiver's HID++ interface and the index the mouse answers on."""
    last_err = None
    for info in (d for d in hid.enumerate(vid) if d["usage_page"] == HIDPP_USAGE_PAGE):
        path = info["path"]
        path = path.decode() if isinstance(path, bytes) else path
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError as exc:
            last_err = exc
            continue
        for index in range(1, 7):
            if _ping(fd, index, read_timeout=ping_timeout):
                return HidppDevice(fd, index, path)
        os.close(fd)
    if isinstance(last_err, PermissionError):
        raise HidppError("found a HID++ interface but cannot open it read/write "
                         "(need rw on /dev/hidraw* -- see the udev rule in the README)")
    raise HidppError("No Logitech HID++ device answered. Is the MX Master 4 on via its Bolt receiver?")


class HidppDevice:
    def __init__(self, fd, device_index, path):
        self.fd = fd
        self.device_index = device_index
        self.path = path

    def fileno(self):
        return self.fd

    def request(self, feature_index, function, params=b"", swid=1, timeout=1.0):
        """Send a function call and return the reply's parameter bytes."""
        addr = (function << 4) | (swid & 0x0F)
        os.write(self.fd, _packet(self.device_index, feature_index, addr, params))
        for _ in range(8):
            resp = _read(self.fd, timeout)
            if not resp:
                raise HidppError("timeout waiting for HID++ response")
            if resp[2] == 0xFF:                              # HID++ 2.0 error report
                raise HidppError(f"device error {resp[5]:#x} on feature {resp[3]:#x}")
            if (resp[1] == self.device_index and resp[2] == feature_index
                    and (resp[3] & 0x0F) == (swid & 0x0F)):
                return resp[4:]
        raise HidppError("no matching HID++ response")

    def write_raw(self, feature_index, addr, data=b""):
        """Fire-and-forget write (haptics). The reply, if any, is read and
        ignored by the event loop (its addr != 0x00, so parse_event drops it)."""
        os.write(self.fd, _packet(self.device_index, feature_index, addr, data))

    def read_event(self, timeout=0.0):
        """Return (feature_index, addr, params) of the next report, or None."""
        data = _read(self.fd, timeout)
        if not data:
            return None
        return (data[2], data[3], data[4:])

    def close(self):
        os.close(self.fd)
