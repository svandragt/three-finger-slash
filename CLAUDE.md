# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Two independent implementations of the same feature — cascade every visible window on the
focused screen, focused window flush left and in front:

- `macos/init.lua` — Hammerspoon config, bound to `cmd+alt+ctrl+/`.
- `linux/three_finger_slash.py` — Python 3 + python-xlib, X11/EWMH, run once per press and
  bound externally (sxhkd/xbindkeys/DE shortcut).

They share no code and cannot — there is no common runtime. What they share is the cascade
formula, deliberately kept identical. **Change the geometry in one and change it in the
other.**

## Commands

```sh
python3 linux/test_cascade.py          # unit tests for the cascade geometry (no X needed)
python3 -m unittest test_cascade.GetWindowPositionTest.test_single_window_fills_top_left_of_work_area  # single test, run from linux/
./linux/three_finger_slash.py          # run the Linux cascade once
./linux/dump_geometry.py               # print the window list, frames and frame extents
```

There is no build or lint step, and no test suite for the macOS side — Lua only runs inside
Hammerspoon.

### Testing the Linux port without a desktop

It can be exercised headlessly against a real reparenting, EWMH-compliant WM, which is the
only way to catch the frame-extents bugs:

```sh
apt-get install -y python3-xlib openbox xterm x11-utils xvfb
export DISPLAY=:99
Xvfb :99 -screen 0 1920x1080x24 & sleep 1; openbox & sleep 1
for i in 1 2 3 4; do xterm -T "win$i" -geometry 80x24+$((i*50))+$((i*50)) -e sleep 600 & sleep 0.5; done
./linux/dump_geometry.py && ./linux/three_finger_slash.py && ./linux/dump_geometry.py
```

Expect x to step down by 40 and y up by 40, with the active window at `x=0`. Note `xterm -T`
is overwritten by the shell unless you pass `-e sleep`, and background X processes do not
survive between separate shell invocations — run the whole sequence in one script.

### Testing the macOS side

Hammerspoon loads `~/.hammerspoon/init.lua`, **not** this repo's file. Symlink it
(`ln -sf "$PWD/macos/init.lua" ~/.hammerspoon/init.lua`), then menu bar icon → Reload Config.
Debug in the Hammerspoon Console. Window management needs Accessibility permission, or every
`hs.window` call silently returns nothing useful.

## The shared cascade formula

For 1-based `index` of `count` windows, step 40px:

- `x = screen.x + (count - index) * 40`, `y = screen.y + (index - 1) * 40`
- `w = min(win.w, screen.w - (count - index) * 40)`
- `h = min(win.h, screen.h - panel_offset - (index - 1) * 40)`

Higher index = further forward = less x offset. The focused window is appended **last**, so
it lands at `x = screen.x` and in front. `panel_offset` is macOS's `menubar_offset = 14`; on
Linux it's 0 because `_NET_WORKAREA` already excludes panels.

## macOS specifics (`macos/init.lua`)

- **`windows` is an intentional global.** `cascade_windows` assigns it without `local` and
  `get_window_position` reads `#windows` for the x offset. Making it `local` breaks the layout
  silently. (The Python port fixes this properly by passing `count` as a parameter.)
- **The layout entry is a positional table** — `hs.layout.apply` expects
  `{application, window, screen, unitrect, framerect, fullframerect}`. Slots 4 and 6 are `nil`
  and slot 5 carries the `hs.geometry.rect`. Don't reorder or drop the `nil`s.

## Linux specifics (`linux/three_finger_slash.py`)

`get_window_position` is pure and is the only unit-tested part. Everything else is EWMH
plumbing in `WindowManager`. Four traps, all of which fail *silently*:

1. **Frame extents.** `get_geometry()` returns the client area relative to the decoration
   frame. `outer_frame()` uses `translate_coords` plus `_NET_FRAME_EXTENTS` to get the outer
   frame in root coordinates; `set_frame()` subtracts the extents again because
   `_NET_MOVERESIZE_WINDOW` positions the frame but sizes the client area. Skip either and
   windows drift by the titlebar height.
2. **Maximized windows ignore `_NET_MOVERESIZE_WINDOW`** — the WM discards the request with no
   error. Hence the unmaximize pass. `dpy.sync()` is *not* enough to know it took effect: it
   round-trips to the X server, not to the WM, and until the WM processes it
   `_NET_FRAME_EXTENTS` still reports the maximized (often borderless) decorations, so sizing
   overshoots by the border width. `wait_until_unpinned()` polls `_NET_WM_STATE` for this.
   That's why the code unmaximizes *all* windows, waits, and only then reads frames.
3. **`_NET_CLIENT_LIST_STACKING`, not `_NET_CLIENT_LIST`.** The latter is creation order.
   Stacking is bottom→top, which is exactly the order the cascade wants. Reversing it
   mirrors the cascade.
4. **`_NET_WORKAREA` is one rect for all monitors** on most WMs. Intersect with the XRandR
   monitor rect and fall back to the raw monitor rect when they don't overlap.

Wayland is rejected up front in `open_display()` — under XWayland the script would see only
XWayland clients, which is worse than refusing.
