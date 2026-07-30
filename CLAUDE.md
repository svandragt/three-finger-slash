# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Hammerspoon (macOS) Lua config that cascades all visible windows on the
focused screen, bound to `cmd+alt+ctrl+/` ("three finger slash").

## Running / testing changes

There is no build, lint, or test suite — the code only runs inside Hammerspoon's embedded
Lua runtime, where the `hs.*` API exists.

Hammerspoon does **not** load this repo's `init.lua`; it loads `~/.hammerspoon/init.lua`.
To iterate:

1. Copy or symlink this file into place, e.g. `ln -sf "$PWD/init.lua" ~/.hammerspoon/init.lua`
2. Reload: Hammerspoon menu bar icon → Reload Config (or `hs.reload()` in the Hammerspoon Console)
3. Press `cmd+alt+ctrl+/` with several windows open on one screen

Debug via the Hammerspoon Console (menu bar icon → Console); `print()` and errors surface
there. Window management requires Accessibility permission for Hammerspoon in System
Settings, or every `hs.window` call silently returns nothing useful.

## Architecture

`init.lua` is three functions plus one `hs.hotkey.bind` at the bottom:

- `get_screen_windows(windows, screen)` — filters to windows on the target screen,
  excluding the desktop and the focused window, then appends the focused window **last**.
  That ordering is load-bearing: last in the list means front of the cascade.
- `get_window_position(win, index)` — computes one entry for `hs.layout.apply`.
- `cascade_windows()` — assembles the layout, `raise()`s each window in order, then
  applies the layout in a single `hs.layout.apply` call.

Two things to know before editing:

- **`windows` is an intentional global.** `cascade_windows` assigns it without `local`, and
  `get_window_position` reads `#windows` to compute the reverse-cascade x offset. Making it
  `local` breaks the layout silently. If you refactor, pass the count in as a parameter.
- **The layout entry is a positional table**, not keyed — `hs.layout.apply` expects
  `{application, window, screen, unitrect, framerect, fullframerect}`. Here slots 4 and 6
  are `nil` and slot 5 carries the `hs.geometry.rect`. Don't reorder or drop the `nil`s.

Cascade geometry lives in two magic numbers: a `40`px step per window in both axes, and
`menubar_offset = 14` subtracted from available height. Windows keep their own width/height
where they fit (`math.min` against the remaining screen space) rather than being forced to a
uniform size.
