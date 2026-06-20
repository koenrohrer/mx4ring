# mx4ring

A from-scratch, Solaar-free clone of the Logitech Options+ **Actions Ring** for
the **MX Master 4** on Linux. It talks HID++ 2.0 directly to the mouse over the
Bolt receiver: it diverts the haptic/gesture button, pops a radial menu at the
cursor, fires the haptic motor, and can remap other buttons to key chords or
shell commands. Tested on GNOME (Wayland); a standalone GTK fallback exists for
wlroots/KDE.

![mx4ring demo](docs/demo.gif)

## Quick start

```bash
git clone https://github.com/koenrohrer/mx4ring.git && cd mx4ring
./setup.sh        # system packages, venv, udev rule, GNOME extension
```

`setup.sh` prints every step, asks before anything that needs `sudo`, and is
safe to re-run. Two things it **can't** do for you:

1. **Unplug and replug the Bolt receiver** — so the new udev ACL applies to it.
2. **Log out and back in** — on Wayland this loads the new extension code and
   activates your new `input`-group membership for `/dev/uinput`.

Then learn your menu button and start the daemon:

```bash
.venv/bin/python discover.py --watch   # press the haptic button; let it save the CID
.venv/bin/python mx4d.py               # press-hold the button, move, release
```

The ring appears at the cursor. Hold the menu button, move toward an item, and
release to run it (or release in the center / press Escape to cancel).

Customise by editing **`config.py`** — the menu items, button remaps, and haptic
waveforms. It is created from `config.example.py` on first run and is gitignored,
so a `git pull` never clobbers your settings.

## How it works (GNOME)

GNOME's Mutter doesn't support the layer-shell protocol a normal client would
need for an at-cursor overlay, and a Wayland client can't read the global cursor
position anyway. The compositor *can*, though — so the menu lives in a GNOME
Shell extension, and the Python daemon (which owns the device) drives it over
D-Bus. Because the menu button is diverted, the compositor never sees its press
*or* release, so the daemon owns both: **press opens, move highlights, release
commits** (a marking-menu / Actions Ring feel).

```
 MX4 buttons ──HID++ divert──▶ mx4d.py (GLib loop owns /dev/hidraw)
   ├─ menu button press ─────▶ D-Bus OpenMenu(items)  + haptic "open"
   ├─ menu button release ───▶ D-Bus CloseMenu        ─┐
   └─ remapped buttons ──────▶ key chord / command (uinput)
                                                        │
 GNOME Shell extension ◀── OpenMenu/CloseMenu ──────────┘
   draws ring at global.get_pointer(), highlights on motion,
   commits on release, and calls back ──▶ Buzz("hover"/"select")
```

| File | Role |
|------|------|
| `setup.sh` | Idempotent installer (packages, venv, udev, extension, service) |
| `hidpp.py` | HID++ transport over a raw hidraw fd (watchable by GLib) |
| `controls.py` | Feature discovery + Reprogrammable Controls v4 (divert buttons) |
| `cid_names.py` | Best-effort CID → human name map (labels standard buttons) |
| `discover.py` | Dump features/controls; `--watch` to learn a button's CID |
| `haptic.py` | Best-effort haptic waveform trigger (reverse-engineered) |
| `uinput_remap.py` | Virtual keyboard for remaps |
| `config.example.py` | Shipped defaults; copied to `config.py` on first run |
| `config.py` | **Your** CIDs, remaps, menu items, haptics (gitignored) |
| `config_loader.py` | Creates `config.py` from the example and validates it |
| `mx4d.py` | The daemon: HID++ loop, diversion, D-Bus service, haptics |
| `gnome-extension/` | The Shell extension that draws the ring at the cursor |
| `ring.py` | Standalone GTK ring — UI test, and the front-end for non-GNOME (wlroots/KDE) |

## Manual setup (what `setup.sh` automates)

Run these yourself if you'd rather not use `setup.sh`, or to understand what it does.

1. System packages first. Debian/Ubuntu mark the system Python as externally
   managed (PEP 668), so you need venv support plus the distro libs (PyGObject
   for `gi`, and the hidapi shared lib):
   ```bash
   sudo apt install python3-full python3-gi libhidapi-hidraw0
   ```
   Then a venv that can still see `python3-gi`, and pip the rest into it:
   ```bash
   python3 -m venv --system-site-packages .venv
   .venv/bin/pip install -r requirements.txt
   source .venv/bin/activate      # so the `python ...` commands below work
   ```
   (If `evdev` fails to build, also `sudo apt install build-essential python3-dev`.)
2. Device access via udev. HID++ needs read **write** on the receiver's hidraw
   node (it's root-only by default), and remaps need `/dev/uinput`:
   ```bash
   sudo tee /etc/udev/rules.d/72-mx4ring.rules >/dev/null <<'EOF'
   # Logitech receivers: grant the logged-in user rw on the HID++ node
   KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="046d", MODE="0660", TAG+="uaccess"
   # uinput for remapped keystrokes
   KERNEL=="uinput", GROUP="input", MODE="0660"
   EOF
   sudo modprobe uinput
   sudo usermod -aG input "$USER"          # for uinput; log out/in afterwards
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```
   Then **unplug and replug the Bolt receiver** so the new rule applies to it.
3. Install the GNOME Shell extension:
   ```bash
   mkdir -p ~/.local/share/gnome-shell/extensions/mx4ring@local
   cp gnome-extension/* ~/.local/share/gnome-shell/extensions/mx4ring@local/
   # On Wayland you must LOG OUT and back IN to load a new extension
   # (you can't restart the shell on Wayland). Then:
   gnome-extensions enable mx4ring@local
   ```
   If it refuses to enable, check your version with `gnome-shell --version` and
   add it to `shell-version` in `metadata.json`.

## Use

```bash
python discover.py            # milestone 1-2: should print device + feature table
python discover.py --watch    # milestone 3: press the haptic button; it offers to
                              #   write MENU_BUTTON_CID into config.py for you
# add any REMAPS / menu items to config.py, then:
python mx4d.py                # milestone 4+: press-hold the button, move, release
```

## Milestone checklist

- [ ] 1. `discover.py` connects and prints the feature table (ping works)
- [ ] 2. The control list shows your buttons with `divertable` flags
- [ ] 3. `--watch` prints a CID when you press the haptic/gesture button
- [ ] 4. Extension installed + enabled; `mx4d.py` running → press-hold the button
       and the ring appears at the cursor; release on an item runs it
- [ ] 5. Haptics fire on open / hover / select (tune the `HAPTIC_ON_*` waveforms;
       see `haptic.py` if silent)
- [ ] 6. A remapped button emits its key/command in both an X11 and a Wayland app
- [ ] 7. Run as a service (below)

## Run as a service

`setup.sh` offers to generate and enable a systemd user service for you (step 5),
filled in with the correct absolute paths for your checkout. To do it by hand,
create the unit using **your** repo path:

```ini
# ~/.config/systemd/user/mx4ring.service
[Unit]
Description=mx4ring daemon
[Service]
ExecStart=/absolute/path/to/mx4ring/.venv/bin/python /absolute/path/to/mx4ring/mx4d.py
Restart=on-failure
[Install]
WantedBy=default.target
```
```bash
systemctl --user enable --now mx4ring
```

## Notes / caveats

- **At-cursor needs the extension.** On GNOME Wayland this is the only way to get
  a true overlay at the pointer (Mutter has no layer-shell; clients can't read the
  global cursor). The compositor can, so the menu lives in the extension.
- **GNOME version sensitivity.** Shell extensions can break across GNOME releases.
  If the ring stops working after a GNOME upgrade, bump `shell-version` in
  `metadata.json` and sanity-check the APIs in `extension.js` (`pushModal`,
  `global.get_pointer`, `Main.layoutManager.uiGroup`).
- **Haptic index is firmware-specific.** `haptic.py` hardcodes `0x0B4E`
  (feature index `0x0B`). If it doesn't buzz, find the haptic feature in
  `discover.py`'s table and update the high byte. The hover "detent" is throttled
  (`HOVER_THROTTLE_US` in `extension.js`) so rapid pointer wiggle can't spam it.
- **Crash leaves buttons diverted.** Re-run `mx4d.py` (it re-diverts on start) or
  power-cycle the mouse to restore defaults.
- **CID names are best-effort.** `cid_names.py` labels standard buttons; the
  MX4's new haptic/gesture control may show as `unknown 0x00xx` — that's the one
  you copy from `--watch` into `MENU_BUTTON_CID`.
- **Non-GNOME?** On wlroots (Hyprland/sway) or KDE, skip the extension and use the
  standalone GTK `ring.py` (layer-shell works there); wire it back into `mx4d.py`
  as the menu front-end instead of the D-Bus signal.

Reverse-engineering references: [mx4notifications](https://github.com/lukasfri/mx4notifications),
[mx4hyprland](https://github.com/MyrikLD/mx4hyprland), and the
[Solaar](https://github.com/pwr-Solaar/Solaar) HID++ implementation.
</content>
</invoke>
