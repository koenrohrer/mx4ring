"""Load, create, and validate the user's ``config.py``.

``config.py`` is gitignored and user-owned; ``config.example.py`` ships the
defaults. On first run we copy the example to ``config.py``, then sanity-check
it so a typo surfaces as a friendly message instead of a traceback.
"""

import os
import re
import shutil

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONFIG = os.path.join(_HERE, "config.py")
_EXAMPLE = os.path.join(_HERE, "config.example.py")


class ConfigError(Exception):
    """A problem with config.py that the user needs to fix."""


def ensure_config():
    """Create config.py from config.example.py on first run."""
    if not os.path.exists(_CONFIG):
        if not os.path.exists(_EXAMPLE):
            raise ConfigError("Neither config.py nor config.example.py exists.")
        shutil.copyfile(_EXAMPLE, _CONFIG)
        print("Created config.py from config.example.py -- edit it to customize.")


def load():
    """Ensure config.py exists, import it, and return the module (no validation)."""
    ensure_config()
    import config
    return config


def _check_leaf(entry, where):
    if not (isinstance(entry, tuple) and len(entry) == 2):
        raise ConfigError(f'{where}: each item must be ("Label", "command"), got {entry!r}')
    label, cmd = entry
    if not isinstance(label, str) or not isinstance(cmd, str):
        raise ConfigError(f'{where}: expected ("Label", "command") strings, got {entry!r}')


def _check_menu(menu, where):
    if not isinstance(menu, list):
        raise ConfigError(f"{where} must be a list of items, got {menu!r}")
    for entry in menu:
        if not (isinstance(entry, tuple) and len(entry) == 2):
            raise ConfigError(f'{where}: each item must be ("Label", action), got {entry!r}')
        label, payload = entry
        if not isinstance(label, str):
            raise ConfigError(f"{where}: label must be a string, got {label!r}")
        if isinstance(payload, str):
            continue                                       # leaf: ("Label", "command")
        if isinstance(payload, list):                      # submenu of leaves
            for child in payload:
                _check_leaf(child, f"{where} -> {label!r} submenu")
        else:
            raise ConfigError(
                f'{where}: {label!r} must map to a "command" string or a list of '
                f'("Label", "command") sub-items, got {payload!r}')


def validate(cfg):
    """Raise ConfigError with a fix-it message if config values are malformed."""
    cid = getattr(cfg, "MENU_BUTTON_CID", None)
    if cid is not None and not isinstance(cid, int):
        raise ConfigError(
            f"MENU_BUTTON_CID must be an int (e.g. 0x01A0) or None, got {cid!r}. "
            f"Run `python discover.py --watch` to find it.")
    for name in ("HAPTIC_ON_OPEN", "HAPTIC_ON_HOVER", "HAPTIC_ON_SELECT"):
        v = getattr(cfg, name, None)
        if v is not None and not (isinstance(v, int) and 0 <= v <= 14):
            raise ConfigError(f"{name} must be an int 0-14 or None, got {v!r}.")
    for key, menu in getattr(cfg, "MENUS", {}).items():
        _check_menu(menu, f"MENUS[{key!r}]")
    return cfg


def set_menu_button_cid(cid):
    """Write MENU_BUTTON_CID into config.py, backing up the old file first.

    Returns the path of the backup. Preserves the line's inline comment.
    """
    ensure_config()
    with open(_CONFIG) as f:
        text = f.read()
    pat = re.compile(r"^(MENU_BUTTON_CID\s*=\s*)\S+(.*)$", flags=re.M)
    if not pat.search(text):
        raise ConfigError("Couldn't find a MENU_BUTTON_CID line in config.py to update.")
    backup = _CONFIG + ".bak"
    shutil.copyfile(_CONFIG, backup)
    text = pat.sub(lambda m: f"{m.group(1)}{cid:#06x}{m.group(2)}", text, count=1)
    with open(_CONFIG, "w") as f:
        f.write(text)
    return backup
