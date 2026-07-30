#!/usr/bin/env python3
"""Debug helper: print the outer frame of every cascadable window, bottom-to-top.

    python3 linux/dump_geometry.py

Useful for checking what the cascade did, and for confirming that frame extents
are being handled correctly on your window manager.
"""

import sys

from Xlib import Xatom

from three_finger_slash import WindowManager, open_display


def title_of(wm, window):
    """Window title, preferring _NET_WM_NAME but falling back to WM_NAME.

    Older clients (xterm among them) only set WM_NAME.
    """
    name = wm.prop(window, "_NET_WM_NAME", wm.dpy.get_atom("UTF8_STRING"))
    if not name:
        name = wm.prop(window, "WM_NAME", Xatom.STRING)
    if not name:
        return "?"
    if isinstance(name, str):
        return name
    return bytes(bytearray(name)).decode("utf-8", "replace")


def main():
    dpy = open_display()
    try:
        wm = WindowManager(dpy)
        desktop = wm.current_desktop()
        active = wm.active_window()
        print(f"work_area={wm.work_area()} monitors={wm.monitors()}")
        for window in wm.stacking_order():
            if not wm.is_cascadable(window, desktop):
                continue
            title = title_of(wm, window)
            marker = " *active" if active is not None and window.id == active.id else ""
            print(
                f"  0x{window.id:08x} {title!r:20} frame={wm.outer_frame(window)} "
                f"extents={wm.frame_extents(window)}{marker}"
            )
    finally:
        dpy.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
