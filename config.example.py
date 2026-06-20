"""Your configuration.

This file ships with neutral defaults. It is copied to ``config.py`` on first
run (``config.py`` is gitignored, so a ``git pull`` never clobbers your edits).
Edit ``config.py``, not this file.

Fill in MENU_BUTTON_CID after running:  python discover.py --watch
(it can also write it here for you). CIDs print as hex (e.g. 0x00c3); they are
stored here as ints.
"""

# --- Device -----------------------------------------------------------------
LOGITECH_VID = 0x046D

# --- The button that opens the radial menu ----------------------------------
# Press the haptic/gesture button during `discover.py --watch`, copy its CID
# (or let --watch write it here for you).
MENU_BUTTON_CID = 0x01A0          # MX Master 4 haptic button

# --- Haptic -----------------------------------------------------------------
# Waveform 0-14 for each moment, or None to disable that one.
#   open   -> ring appears
#   hover  -> pointer crosses into a new item (a "detent" tick; throttled)
#   select -> you commit a choice
HAPTIC_ON_OPEN = 1
HAPTIC_ON_HOVER = 0
HAPTIC_ON_SELECT = 3

# --- Extra button remaps (CID -> action) ------------------------------------
# Action is one of:
#   ("keys", ["KEY_LEFTCTRL", "KEY_C"])          -> emit a key chord via uinput
#   ("exec", "loginctl lock-session")            -> run a shell command
REMAPS = {
    # 0x00C4: ("keys", ["KEY_LEFTMETA"]),
    # 0x00D7: ("exec", "loginctl lock-session"),
}

# --- Radial menu items -------------------------------------------------------
# An item is either a leaf      ("Label", "shell command")
# or a submenu (drills in)      ("Label", [ ("Child", "cmd"), ... ])
MENUS = {
    "default": [
        ("Files",      "nautilus || xdg-open ~"),
        ("Screenshot", "gdbus call --session --dest org.freedesktop.portal.Desktop "
                       "--object-path /org/freedesktop/portal/desktop "
                       "--method org.freedesktop.portal.Screenshot.Screenshot "
                       "\"\" \"{'interactive': <true>}\""),
        ("Lock",       "loginctl lock-session"),
        ("Settings",   "gnome-control-center"),
    ],
}

# Examples -- copy entries into "default" above and edit:
#   ("VS Code", "code -n"),                       # a leaf that launches an app
#   ("Browser", "xdg-open https://example.com"),  # a leaf that opens a URL
#   ("Apps", [                                    # a submenu (drills in)
#       ("Editor",   "code -n"),
#       ("Terminal", "kgx"),
#   ]),
