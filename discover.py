#!/usr/bin/env python3
"""Discovery tool -- clears milestones 1-3.

    python discover.py            # ping, dump feature table + control list
    python discover.py --watch    # divert buttons, print the CID of whatever you press

In --watch, left/right click are left alone so the mouse stays usable.
Press Ctrl-C to restore the buttons.
"""

import signal
import sys

import config_loader
from cid_names import name_for
from controls import ReprogControls, list_features
from hidpp import open_device

SKIP = {0x0050, 0x0051}  # left / right click -- keep usable while watching


def offer_write_cid(cid):
    """Offer to save this CID as MENU_BUTTON_CID in config.py. Returns True if written."""
    try:
        ans = input("    Set this as MENU_BUTTON_CID in config.py? [y/N] ").strip().lower()
    except EOFError:
        return False
    if ans not in ("y", "yes"):
        print("    Ok -- still watching. Press Ctrl-C when you're done.\n")
        return False
    backup = config_loader.set_menu_button_cid(cid)
    print(f"    Wrote MENU_BUTTON_CID = {cid:#06x} to config.py (backup: {backup}).\n")
    return True


def main():
    dev = open_device()
    print(f"Connected: device index {dev.device_index} via {dev.path!r}\n")

    print("HID++ features (index : id : version):")
    for index, fid, ver in list_features(dev):
        print(f"  {index:#04x} : {fid:#06x} : v{ver}")
    print()

    rc = ReprogControls.open(dev)
    controls = rc.controls()
    print(f"Reprogrammable controls ({len(controls)}):")
    for c in controls:
        tags = [t for t, on in (("divertable", c.divertable),
                                ("persist", c.persist_divertable)) if on]
        print(f"  cid={c.cid:#06x} {name_for(c.cid):<28} pos={c.pos} [{', '.join(tags) or '-'}]")
    print()

    if "--watch" not in sys.argv:
        print("Re-run with --watch and press a button to learn its CID.")
        return

    targets = [c.cid for c in controls if c.divertable and c.cid not in SKIP]
    for cid in targets:
        rc.set_divert(cid, True)

    def restore(*_):
        for cid in targets:
            try:
                rc.set_divert(cid, False)
            except Exception:
                pass
        print("\nRestored. Bye.")
        sys.exit(0)

    signal.signal(signal.SIGINT, restore)
    print(f"Diverted {len(targets)} buttons. Press one to see its CID. Ctrl-C to stop.\n")

    held = set()
    offered = False
    while True:
        ev = dev.read_event(timeout=0.5)
        if not ev:
            continue
        cids = rc.parse_event(*ev[1:])
        if cids is None:
            continue
        for cid in cids - held:
            print(f"  pressed  {cid:#06x}  {name_for(cid)}")
            if not offered:
                offered = True
                if offer_write_cid(cid):
                    restore()        # config written; un-divert and exit
        held = cids


if __name__ == "__main__":
    main()
