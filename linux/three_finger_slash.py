#!/usr/bin/env python3
"""Cascading Windows: all windows, neatly organised. Linux/X11 port of the
Hammerspoon script in ../macos/init.lua.

Arranges every visible window on the focused monitor in a reverse cascade, with
the focused window aligned to the left and brought to the front.

Run it once per invocation; bind it to a key with sxhkd, xbindkeys or your
desktop's own shortcut settings (see ../README.md).
"""

import os
import sys
import time

try:
    from Xlib import X, Xatom, display, error
    from Xlib.protocol import event
except ImportError:
    sys.exit(
        "python-xlib is required: install python3-xlib (Debian/Ubuntu), "
        "python3-xlib (Fedora) or `pip install python-xlib`."
    )

# Cascade step, in pixels, between successive windows on both axes.
STEP = 40

# The macOS original subtracts 14px for the menu bar. On X11 the panel/dock area
# is already excluded by _NET_WORKAREA, so no extra offset is needed. Raise this
# if your window manager does not report a work area and windows sit under a panel.
PANEL_OFFSET = 0

# Windows of these types are never part of the cascade.
SKIP_WINDOW_TYPES = (
    "_NET_WM_WINDOW_TYPE_DESKTOP",
    "_NET_WM_WINDOW_TYPE_DOCK",
    "_NET_WM_WINDOW_TYPE_SPLASH",
    "_NET_WM_WINDOW_TYPE_NOTIFICATION",
)

# _NET_WM_DESKTOP value meaning "show on all desktops".
ALL_DESKTOPS = 0xFFFFFFFF

# States that stop a window being freely moved or resized.
PINNED_STATES = (
    "_NET_WM_STATE_MAXIMIZED_VERT",
    "_NET_WM_STATE_MAXIMIZED_HORZ",
    "_NET_WM_STATE_FULLSCREEN",
)

# How long to wait for the window manager to act on an unmaximize request.
SETTLE_TIMEOUT = 0.5

# _NET_MOVERESIZE_WINDOW flags: gravity 0 (use the window's own) plus a bit per
# supplied field (x, y, width, height) in bits 8-11, and source "pager" in 12-13.
MOVERESIZE_FLAGS = (1 << 8) | (1 << 9) | (1 << 10) | (1 << 11) | (2 << 12)


class Rect:
    """A rectangle in root-window coordinates."""

    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = int(x), int(y), int(w), int(h)

    @property
    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def intersect(self, other):
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.x + self.w, other.x + other.w)
        y2 = min(self.y + self.h, other.y + other.h)
        if x2 <= x1 or y2 <= y1:
            return None
        return Rect(x1, y1, x2 - x1, y2 - y1)

    def contains(self, point):
        px, py = point
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def __eq__(self, other):
        return (self.x, self.y, self.w, self.h) == (other.x, other.y, other.w, other.h)

    def __repr__(self):
        return f"Rect(x={self.x}, y={self.y}, w={self.w}, h={self.h})"


def get_window_position(win_frame, index, count, screen_frame, panel_offset=PANEL_OFFSET):
    """Return the target Rect for the window at 1-based `index` of `count`.

    Pure function -- the same reverse-cascade formula as get_window_position in
    ../macos/init.lua, and the only part of this script that needs no X server.

    Higher index means further forward: less x offset (so the front window is
    flush left, keeping every title visible) and more y offset. Windows keep
    their own size wherever it still fits on screen. The back-most window
    (index 1 of more than one) is flush right instead, moved rather than
    resized, so it doesn't leave a gap when it's narrower than its step.
    """
    y_offset = (index - 1) * STEP
    height = min(win_frame.h, screen_frame.h - panel_offset - y_offset)
    if index == 1 and count > 1:
        width = min(win_frame.w, screen_frame.w)
        return Rect(screen_frame.x + screen_frame.w - width, screen_frame.y, width, height)
    x_offset = (count - index) * STEP
    return Rect(
        screen_frame.x + x_offset,
        screen_frame.y + y_offset,
        min(win_frame.w, screen_frame.w - x_offset),
        height,
    )


class WindowManager:
    """Thin EWMH wrapper: the X11 stand-in for Hammerspoon's hs.window/hs.screen."""

    def __init__(self, dpy):
        self.dpy = dpy
        self.root = dpy.screen().root
        self._atoms = {}

    def atom(self, name):
        if name not in self._atoms:
            self._atoms[name] = self.dpy.get_atom(name)
        return self._atoms[name]

    def prop(self, window, name, kind=Xatom.CARDINAL):
        """Read a property, returning its value list or [] if absent."""
        try:
            reply = window.get_full_property(self.atom(name), kind)
        except (error.BadWindow, error.BadAtom):
            return []
        return list(reply.value) if reply else []

    # -- window enumeration ------------------------------------------------

    def stacking_order(self):
        """Windows bottom-to-top.

        _NET_CLIENT_LIST_STACKING, not _NET_CLIENT_LIST: the latter is creation
        order, which would cascade windows in an arbitrary sequence. Bottom-to-top
        is exactly the order the cascade wants, since later indices land nearer
        the front.
        """
        ids = self.prop(self.root, "_NET_CLIENT_LIST_STACKING", Xatom.WINDOW)
        return [self.dpy.create_resource_object("window", wid) for wid in ids]

    def active_window(self):
        ids = self.prop(self.root, "_NET_ACTIVE_WINDOW", Xatom.WINDOW)
        if not ids or ids[0] == X.NONE:
            return None
        return self.dpy.create_resource_object("window", ids[0])

    def is_cascadable(self, window, current_desktop):
        """True for windows Hammerspoon's visibleWindows() would have returned."""
        types = self.prop(window, "_NET_WM_WINDOW_TYPE", Xatom.ATOM)
        if any(self.atom(name) in types for name in SKIP_WINDOW_TYPES):
            return False

        # Minimized/shaded windows are absent from visibleWindows() on macOS.
        state = self.prop(window, "_NET_WM_STATE", Xatom.ATOM)
        if self.atom("_NET_WM_STATE_HIDDEN") in state:
            return False

        # Only the current desktop, mirroring "the focused screen's Space".
        desktop = self.prop(window, "_NET_WM_DESKTOP")
        if desktop and desktop[0] != ALL_DESKTOPS and desktop[0] != current_desktop:
            return False

        return True

    def current_desktop(self):
        value = self.prop(self.root, "_NET_CURRENT_DESKTOP")
        return value[0] if value else 0

    # -- geometry ----------------------------------------------------------

    def frame_extents(self, window):
        """Decoration thickness as (left, right, top, bottom)."""
        extents = self.prop(window, "_NET_FRAME_EXTENTS")
        if len(extents) < 4:
            return 0, 0, 0, 0
        return tuple(int(v) for v in extents[:4])

    def outer_frame(self, window):
        """The window's outer frame in root coordinates, decorations included.

        get_geometry() reports the *client* area relative to its parent, which
        under a reparenting window manager is the decoration frame rather than
        the root -- hence translate_coords, plus _NET_FRAME_EXTENTS to grow the
        client rect out to the frame that Hammerspoon's win:frame() describes.
        """
        try:
            geom = window.get_geometry()
            origin = window.translate_coords(self.root, 0, 0)
        except (error.BadWindow, error.BadDrawable):
            return None
        left, right, top, bottom = self.frame_extents(window)
        return Rect(
            -origin.x - left,
            -origin.y - top,
            geom.width + left + right,
            geom.height + top + bottom,
        )

    def monitors(self):
        """Monitor rectangles via XRandR, falling back to the whole X screen."""
        try:
            reply = self.root.xrandr_get_monitors()
            rects = [Rect(m.x, m.y, m.width_in_pixels, m.height_in_pixels) for m in reply.monitors]
            if rects:
                return rects
        except (AttributeError, error.XError):
            pass
        screen = self.dpy.screen()
        return [Rect(0, 0, screen.width_in_pixels, screen.height_in_pixels)]

    def work_area(self):
        """The panel-free area, or None if the window manager doesn't publish one."""
        area = self.prop(self.root, "_NET_WORKAREA")
        if len(area) < 4:
            return None
        return Rect(*area[:4])

    def screen_frame(self, window):
        """Usable area of the monitor holding `window`.

        _NET_WORKAREA is a single rect spanning all monitors on most window
        managers, so intersect it with the monitor -- and ignore it if the two
        don't overlap, which happens on multi-monitor setups where the work area
        only describes the primary display.
        """
        frame = self.outer_frame(window)
        monitors = self.monitors()
        monitor = next(
            (m for m in monitors if frame and m.contains(frame.center)), monitors[0]
        )
        area = self.work_area()
        if area is None:
            return monitor
        return monitor.intersect(area) or monitor

    # -- window actions ----------------------------------------------------

    def client_message(self, window, name, data):
        """Send a 32-bit client message to the root window, as EWMH requires."""
        payload = (list(data) + [0, 0, 0, 0, 0])[:5]
        self.root.send_event(
            event.ClientMessage(
                window=window, client_type=self.atom(name), data=(32, payload)
            ),
            event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask,
        )

    def pinned_states(self, window):
        state = self.prop(window, "_NET_WM_STATE", Xatom.ATOM)
        return [self.atom(name) for name in PINNED_STATES if self.atom(name) in state]

    def unmaximize(self, window):
        """Drop maximized/fullscreen states.

        A maximized window silently ignores _NET_MOVERESIZE_WINDOW -- the window
        manager discards the request with no error -- so this has to happen first.
        """
        present = self.pinned_states(window)
        if not present:
            return
        # _NET_WM_STATE carries at most two properties per message; 0 == remove.
        for i in range(0, len(present), 2):
            self.client_message(window, "_NET_WM_STATE", [0] + present[i : i + 2] + [1])

    def wait_until_unpinned(self, windows, timeout=SETTLE_TIMEOUT):
        """Block until the window manager has actually applied the unmaximize.

        dpy.sync() only round-trips to the X server; it says nothing about whether
        the window manager has processed the client message yet. Until it has,
        _NET_FRAME_EXTENTS still reports the maximized decorations (openbox drops
        the borders when maximized), and sizing against those stale extents
        overshoots by the border width. So poll the state instead of assuming.
        """
        deadline = time.monotonic() + timeout
        pending = list(windows)
        while pending:
            pending = [w for w in pending if self.pinned_states(w)]
            if not pending or time.monotonic() >= deadline:
                break
            time.sleep(0.02)
        return not pending

    def raise_window(self, window):
        try:
            window.configure(stack_mode=X.Above)
        except error.BadWindow:
            pass

    def activate(self, window):
        self.client_message(window, "_NET_ACTIVE_WINDOW", [2, X.CurrentTime, 0])

    def set_frame(self, window, rect):
        """Move/resize so the window's *outer* frame matches `rect`.

        _NET_MOVERESIZE_WINDOW positions the frame but sizes the client area, so
        the decorations come back off the width and height here.
        """
        left, right, top, bottom = self.frame_extents(window)
        width = max(1, rect.w - left - right)
        height = max(1, rect.h - top - bottom)
        self.client_message(
            window, "_NET_MOVERESIZE_WINDOW", [MOVERESIZE_FLAGS, rect.x, rect.y, width, height]
        )


def get_screen_windows(wm, windows, screen_frame, focused):
    """Windows on `screen_frame`, focused one last.

    Same contract as get_screen_windows in ../macos/init.lua: skip the desktop
    and the focused window while filtering, then append the focused window so it
    ends up at the front of the cascade.
    """
    desktop = wm.current_desktop()
    result = []
    for window in windows:
        if focused is not None and window.id == focused.id:
            continue
        if not wm.is_cascadable(window, desktop):
            continue
        frame = wm.outer_frame(window)
        if frame is None or not screen_frame.contains(frame.center):
            continue
        result.append(window)

    if focused is not None:
        result.append(focused)
    return result


def cascade_windows(wm):
    focused = wm.active_window()
    if focused is None:
        return "no active window -- focus a window first"

    screen_frame = wm.screen_frame(focused)
    windows = get_screen_windows(wm, wm.stacking_order(), screen_frame, focused)
    if not windows:
        return "no visible windows on this screen"

    # Unmaximize everything first and let the window manager catch up, so that the
    # frames and frame extents read below describe restored windows. The macOS
    # version likewise builds the whole layout before applying it in one go.
    for window in windows:
        wm.unmaximize(window)
    wm.dpy.sync()
    wm.wait_until_unpinned(windows)

    count = len(windows)
    for index, window in enumerate(windows, start=1):
        frame = wm.outer_frame(window)
        if frame is None:
            continue
        wm.raise_window(window)
        wm.set_frame(window, get_window_position(frame, index, count, screen_frame))

    # The focused window is last in the list, so this leaves it in front.
    wm.activate(windows[-1])
    wm.dpy.sync()
    return None


def open_display():
    """Connect to X11, refusing Wayland rather than half-working under XWayland."""
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        sys.exit(
            "This is an X11 port and cannot manage a Wayland session. Under XWayland "
            "it would only see XWayland clients. Log into an X11/Xorg session instead."
        )
    try:
        return display.Display()
    except (error.DisplayError, error.ConnectionClosedError) as exc:
        sys.exit(f"cannot open X display (is DISPLAY set?): {exc}")


def main():
    dpy = open_display()
    try:
        problem = cascade_windows(WindowManager(dpy))
    finally:
        dpy.close()
    if problem:
        sys.exit(f"three-finger-slash: {problem}")


if __name__ == "__main__":
    main()
