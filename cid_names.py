"""Best-effort CID -> human name lookup (subset of Solaar's CONTROL table).

Note: the MX Master 4's *new* haptic/gesture control may not be listed here --
new hardware gets new CIDs. So this labels the standard buttons; you'll still
identify the new one by pressing it in `discover.py --watch`.
"""

CID_NAMES = {
    0x0050: "Left Click",
    0x0051: "Right Click",
    0x0052: "Middle Button",
    0x0053: "Back Button",
    0x0056: "Forward Button",
    0x00C3: "Mouse Gesture Button",
    0x00C4: "Smart Shift",
    0x00C5: "Microphone",
    0x00D0: "MultiPlatform Gesture Button",
    0x00D1: "Host Switch Channel 1",
    0x00D2: "Host Switch Channel 2",
    0x00D3: "Host Switch Channel 3",
    0x00D7: "Virtual Gesture Button",
    0x00ED: "DPI Change",
    0x00E5: "Play/Pause",
    0x00E8: "Volume Down",
    0x00E9: "Volume Up",
    0x0003: "Mute",
}


def name_for(cid):
    return CID_NAMES.get(cid, f"unknown {cid:#06x}")
