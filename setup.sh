#!/usr/bin/env bash
# mx4ring setup -- idempotent installer.
#
# Prints each step before running it, asks before anything that needs sudo, and
# is safe to re-run. It CANNOT replug your receiver or log you out; those manual
# steps are listed at the end.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
VENV="$REPO_DIR/.venv"
EXT_UUID="mx4ring@local"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"
UDEV_RULE="/etc/udev/rules.d/72-mx4ring.rules"

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }

# Ask a yes/no question, reading from the terminal even if stdin is piped.
ask() {  # ask "prompt" "default(Y|N)"  -> returns 0 for yes
  local prompt="$1" def="${2:-Y}" ans
  read -r -p "   $prompt " ans </dev/tty || ans=""
  ans="${ans:-$def}"
  [[ "$ans" =~ ^[Yy] ]]
}

# Run a privileged command, but show it and ask first.
run_sudo() {
  printf '\n   The next step needs sudo:\n     sudo %s\n' "$*"
  if ask "Run it? [Y/n]" Y; then
    sudo "$@"
  else
    info "Skipped. (Re-run setup.sh later to finish.)"
    return 1
  fi
}

# --- 1. System packages -----------------------------------------------------
say "1/5  System packages"
if command -v apt >/dev/null 2>&1; then
  PKGS=(python3-full python3-gi libhidapi-hidraw0 build-essential python3-dev)
  info "apt detected -> ${PKGS[*]}"
  run_sudo apt install -y "${PKGS[@]}" || true
elif command -v pacman >/dev/null 2>&1; then
  PKGS=(python python-gobject hidapi base-devel)
  info "pacman detected -> ${PKGS[*]}"
  run_sudo pacman -S --needed "${PKGS[@]}" || true
elif command -v dnf >/dev/null 2>&1; then
  PKGS=(python3 python3-gobject hidapi gcc python3-devel)
  info "dnf detected -> ${PKGS[*]}"
  run_sudo dnf install -y "${PKGS[@]}" || true
else
  info "No apt/pacman/dnf found. Install these yourself, then re-run:"
  info "  a Python venv module, PyGObject (gi), the hidapi shared lib, and a C toolchain."
fi

# --- 2. Python virtualenv + config ------------------------------------------
say "2/5  Python virtualenv ($VENV)"
if [ -d "$VENV" ]; then
  info "venv already exists -- reusing it."
else
  info "Creating venv with --system-site-packages (so it can see python3-gi)..."
  python3 -m venv --system-site-packages "$VENV"
fi
info "Installing Python requirements into the venv..."
"$VENV/bin/pip" install -q -r "$REPO_DIR/requirements.txt"
if [ ! -f "$REPO_DIR/config.py" ]; then
  cp "$REPO_DIR/config.example.py" "$REPO_DIR/config.py"
  info "Created config.py from config.example.py -- edit it to customize."
fi

# --- 3. Device access (udev + uinput) ---------------------------------------
say "3/5  Device access (udev rule + uinput)"
read -r -d '' RULE <<'EOF' || true
# Logitech receivers: grant the logged-in user rw on the HID++ node
KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{idVendor}=="046d", MODE="0660", TAG+="uaccess"
# uinput for remapped keystrokes
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF
if [ -f "$UDEV_RULE" ] && diff -q <(printf '%s\n' "$RULE") "$UDEV_RULE" >/dev/null 2>&1; then
  info "udev rule already installed at $UDEV_RULE."
else
  info "Installing udev rule to $UDEV_RULE ..."
  TMP_RULE="$(mktemp)"
  printf '%s\n' "$RULE" > "$TMP_RULE"
  run_sudo install -m 0644 "$TMP_RULE" "$UDEV_RULE" || true
  rm -f "$TMP_RULE"
fi
run_sudo modprobe uinput || true
if id -nG "$USER" | tr ' ' '\n' | grep -qx input; then
  info "You're already in the 'input' group."
else
  run_sudo usermod -aG input "$USER" || true
  info "Added you to 'input' -- this needs a log out/in to take effect."
fi
run_sudo udevadm control --reload-rules || true
run_sudo udevadm trigger || true

# --- 4. GNOME Shell extension -----------------------------------------------
say "4/5  GNOME Shell extension"
info "Copying extension to $EXT_DIR ..."
mkdir -p "$EXT_DIR"
cp "$REPO_DIR"/gnome-extension/* "$EXT_DIR/"
if command -v gnome-extensions >/dev/null 2>&1; then
  if gnome-extensions enable "$EXT_UUID" 2>/dev/null; then
    info "Enabled $EXT_UUID."
  else
    info "Couldn't enable yet -- on Wayland you must log out/in first, then run:"
    info "  gnome-extensions enable $EXT_UUID"
  fi
else
  info "gnome-extensions CLI not found -- enable it from the Extensions app after relog."
fi

# --- 5. systemd user service (optional) -------------------------------------
say "5/5  Run as a service (optional)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/mx4ring.service"
info "This runs the daemon at login, from $REPO_DIR."
if ask "Install + enable the systemd user service now? [y/N]" N; then
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT" <<EOF
[Unit]
Description=mx4ring daemon

[Service]
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV/bin/python $REPO_DIR/mx4d.py
Restart=on-failure

[Install]
WantedBy=default.target
EOF
  systemctl --user daemon-reload
  if systemctl --user enable --now mx4ring.service; then
    info "Service enabled."
  else
    info "Wrote $UNIT, but enabling failed. Start it later with:"
    info "  systemctl --user enable --now mx4ring"
  fi
else
  info "Skipped. Run the daemon directly with:"
  info "  $VENV/bin/python $REPO_DIR/mx4d.py"
fi

# --- Done -------------------------------------------------------------------
say "Done -- manual steps a script can't do"
cat <<EOF
   1. Unplug and replug the Bolt receiver, so the new udev ACL applies to it.
   2. Log OUT and back IN (Wayland) -- this loads the new extension code AND
      activates your 'input' group membership for /dev/uinput.

   After that:
     - Find your menu button's CID:  $VENV/bin/python discover.py --watch
       (press the haptic button; let it write MENU_BUTTON_CID for you)
     - Run it:                       $VENV/bin/python mx4d.py
       (or rely on the systemd service if you enabled it above)

   Usual culprits if something doesn't work:
     - "externally-managed-environment" (PEP 668): the venv above avoids it;
       don't pip into the system Python.
     - evdev fails to build: install your distro's C toolchain + Python headers
       (apt: build-essential python3-dev / dnf: gcc python3-devel / pacman: base-devel).
     - No device / no haptics: replug the receiver (step 1) and make sure the
       mouse is awake on its Bolt channel (give it a wiggle).
     - Extension won't enable: you skipped the Wayland relog (step 2), or your
       GNOME version isn't listed in gnome-extension/metadata.json's shell-version.
EOF
