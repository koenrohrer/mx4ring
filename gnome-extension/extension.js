// mx4ring GNOME Shell extension (GNOME 45+).
//
// Listens on the session bus for the mx4ring daemon's OpenMenu/CloseMenu
// signals, draws a radial menu at the pointer, highlights the sector the
// pointer moves toward, and commits the choice on release (press-hold-move-
// release). It calls back into the daemon's Buzz method for hover/select
// haptics -- the daemon is the sole owner of the HID++ device.
//
// Menus can nest one level: an item with children is a submenu. Moving onto it
// drills in (the ring swaps to the children); moving back to the centre pops up
// a level. Releasing over a leaf runs its command.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const BUS_NAME = 'dev.mx4ring.Daemon';
const OBJ_PATH = '/dev/mx4ring/Daemon';
const IFACE = 'dev.mx4ring.Daemon';

const R_IN = 62;               // inner hole / deadzone radius (px)
const R_OUT = 168;             // outer wheel radius (px)
const R_MID = (R_IN + R_OUT) / 2;   // radius the labels sit at
const PAD = 6;                 // breathing room for the outer stroke
const HOVER_THROTTLE_US = 40000;

export default class Mx4RingExtension extends Extension {
    enable() {
        this._bus = Gio.DBus.session;
        this._overlay = null;
        this._area = null;
        this._items = [];
        this._buttons = [];
        this._stack = [];
        this._selected = -1;
        this._cx = 0;
        this._cy = 0;
        this._grab = null;
        this._lastHover = 0;

        this._openId = this._bus.signal_subscribe(
            BUS_NAME, IFACE, 'OpenMenu', OBJ_PATH, null,
            Gio.DBusSignalFlags.NONE,
            (_c, _s, _p, _i, _sig, params) => this._open(params.recursiveUnpack()[0]));

        this._closeId = this._bus.signal_subscribe(
            BUS_NAME, IFACE, 'CloseMenu', OBJ_PATH, null,
            Gio.DBusSignalFlags.NONE,
            () => this._commit());
    }

    disable() {
        this._close();
        if (this._openId)
            this._bus.signal_unsubscribe(this._openId);
        if (this._closeId)
            this._bus.signal_unsubscribe(this._closeId);
        this._openId = this._closeId = 0;
        this._bus = null;
    }

    _buzz(kind) {
        this._bus.call(BUS_NAME, OBJ_PATH, IFACE, 'Buzz',
            new GLib.Variant('(s)', [kind]), null,
            Gio.DBusCallFlags.NO_AUTO_START, -1, null, null);
    }

    // Turn the raw D-Bus payload (label, command, children[]) into normalized
    // {label, command, children} objects. Children are always leaves here.
    _normalize(raw) {
        return raw.map(it => ({
            label: it[0],
            command: it[1],
            children: (it[2] || []).map(c => ({label: c[0], command: c[1], children: []})),
        }));
    }

    _open(raw) {
        if (this._overlay || !raw || raw.length === 0)
            return;
        this._stack = [];

        const [px, py] = global.get_pointer();
        this._cx = px;
        this._cy = py;

        this._overlay = new St.Widget({
            reactive: true,
            can_focus: true,
            x: 0,
            y: 0,
            width: global.stage.width,
            height: global.stage.height,
            style_class: 'mx4-overlay',
        });
        Main.layoutManager.uiGroup.add_child(this._overlay);

        const size = 2 * (R_OUT + PAD);
        this._area = new St.DrawingArea({
            width: size,
            height: size,
            reactive: false,
        });
        this._area.set_position(Math.round(px - size / 2), Math.round(py - size / 2));
        this._area.connect('repaint', a => this._drawWheel(a));
        this._overlay.add_child(this._area);

        this._overlay.connect('notify::allocation', () => this._recenter());
        this._overlay.connect('motion-event', (_a, ev) => {
            const [x, y] = ev.get_coords();
            this._update(x, y);
            return Clutter.EVENT_STOP;
        });
        this._overlay.connect('button-press-event', () => {
            this._commit();
            return Clutter.EVENT_STOP;
        });
        this._overlay.connect('key-press-event', (_a, ev) => {
            if (ev.get_key_symbol() === Clutter.KEY_Escape)
                this._close();
            return Clutter.EVENT_STOP;
        });

        this._buttons = [];
        this._setItems(this._normalize(raw));

        this._grab = Main.pushModal(this._overlay);
        this._overlay.grab_key_focus();
    }

    // Display a level: rebuild the labels for `items`, reset selection, repaint.
    _setItems(items) {
        for (const chip of this._buttons)
            chip.destroy();
        this._items = items;
        this._selected = -1;
        const n = items.length;
        this._buttons = items.map((item, i) => {
            const angle = -Math.PI / 2 + 2 * Math.PI * i / n;
            const chip = new St.Label({text: item.label, style_class: 'mx4-item'});
            chip._cx = this._cx + R_MID * Math.cos(angle);
            chip._cy = this._cy + R_MID * Math.sin(angle);
            this._overlay.add_child(chip);
            return chip;
        });
        this._recenter();
        if (this._area)
            this._area.queue_repaint();
    }

    // Draw a connected donut: a dark wedge per item, the hovered one filled in
    // accent, separated by radial dividers and bounded by inner/outer rings.
    _drawWheel(area) {
        const cr = area.get_context();
        const sf = St.ThemeContext.get_for_stage(global.stage).scaleFactor;
        const [w, h] = area.get_surface_size();
        const cx = w / 2;
        const cy = h / 2;
        const rIn = R_IN * sf;
        const rOut = R_OUT * sf;
        const n = this._items.length;
        const half = Math.PI / n;

        for (let i = 0; i < n; i++) {
            const a = -Math.PI / 2 + 2 * Math.PI * i / n;
            cr.newSubPath();
            cr.arc(cx, cy, rOut, a - half, a + half);
            cr.arcNegative(cx, cy, rIn, a + half, a - half);
            cr.closePath();
            if (i === this._selected)
                cr.setSourceRGBA(0.20, 0.55, 0.95, 0.92);
            else if (this._items[i].children.length)
                cr.setSourceRGBA(0.16, 0.16, 0.22, 0.85);   // submenu wedge: a touch lighter
            else
                cr.setSourceRGBA(0.12, 0.12, 0.14, 0.82);
            cr.fill();
        }

        // radial dividers between wedges
        cr.setSourceRGBA(1, 1, 1, 0.16);
        cr.setLineWidth(Math.max(1, 1.5 * sf));
        for (let i = 0; i < n; i++) {
            const b = -Math.PI / 2 + 2 * Math.PI * i / n - half;
            cr.moveTo(cx + rIn * Math.cos(b), cy + rIn * Math.sin(b));
            cr.lineTo(cx + rOut * Math.cos(b), cy + rOut * Math.sin(b));
        }
        cr.stroke();

        // inner + outer rings
        cr.setSourceRGBA(1, 1, 1, 0.22);
        cr.setLineWidth(Math.max(1, 2 * sf));
        cr.arc(cx, cy, rOut, 0, 2 * Math.PI);
        cr.stroke();
        cr.arc(cx, cy, rIn, 0, 2 * Math.PI);
        cr.stroke();

        cr.$dispose();
    }

    _recenter() {
        for (const chip of this._buttons) {
            chip.set_position(
                Math.round(chip._cx - chip.width / 2),
                Math.round(chip._cy - chip.height / 2));
        }
    }

    _update(x, y) {
        const dx = x - this._cx;
        const dy = y - this._cy;
        let idx = -1;
        if (Math.hypot(dx, dy) >= R_IN) {
            let ang = Math.atan2(dy, dx) + Math.PI / 2;
            if (ang < 0)
                ang += 2 * Math.PI;
            const n = this._items.length;
            idx = Math.floor(((ang + Math.PI / n) % (2 * Math.PI)) / (2 * Math.PI) * n) % n;
        }

        if (idx < 0) {
            // centre deadzone: pop up a level if we're in a submenu, else clear.
            if (this._stack.length) {
                this._setItems(this._stack.pop());
            } else if (this._selected !== -1) {
                this._selected = -1;
                this._area.queue_repaint();
                this._buttons.forEach(c => c.remove_style_class_name('mx4-selected'));
            }
            return;
        }

        const item = this._items[idx];
        if (item.children.length) {
            // drill into the submenu: the ring swaps to its children.
            this._stack.push(this._items);
            this._setItems(item.children);
            this._buzz('hover');
            return;
        }

        if (idx === this._selected)
            return;
        this._selected = idx;
        this._area.queue_repaint();
        this._buttons.forEach((c, i) => {
            if (i === idx)
                c.add_style_class_name('mx4-selected');
            else
                c.remove_style_class_name('mx4-selected');
        });
        const now = GLib.get_monotonic_time();
        if (now - this._lastHover >= HOVER_THROTTLE_US) {
            this._lastHover = now;
            this._buzz('hover');
        }
    }

    _commit() {
        const idx = this._selected;
        const items = this._items;
        this._close();
        if (idx >= 0 && idx < items.length && items[idx].command) {
            this._buzz('select');
            try {
                Gio.Subprocess.new(['sh', '-c', items[idx].command], Gio.SubprocessFlags.NONE);
            } catch (e) {
                logError(e, 'mx4ring: failed to launch command');
            }
        }
    }

    _close() {
        if (this._grab) {
            Main.popModal(this._grab);
            this._grab = null;
        }
        if (this._overlay) {
            this._overlay.destroy();
            this._overlay = null;
        }
        this._area = null;
        this._buttons = [];
        this._stack = [];
        this._selected = -1;
    }
}
