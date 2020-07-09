-- Cascading Windows: All windows, neatly organised using HammerSpoon (http://www.hammerspoon.org/)
hs.loadSpoon("SpoonInstall")

function get_screen_windows(windows, screen)
    local focused_wins = {}
    
    -- Process those windows on the screen, excluding desktop
    for i, win in ipairs(windows) do
        if win:screen():getUUID() == screen:getUUID() then
            if win ~= hs.window.desktop() then
                focused_wins[#focused_wins + 1] = win
            end
        end
    end
    return focused_wins
end

function get_window_position(win, index)
    local menubar_offset = 14
    
    local screen = win:screen()
    local screen_frame = screen:frame()
    local win_frame = win:frame()
    
    local win_pos = {
        win:application(),
        win,
        screen,
        nil,
        hs.geometry.rect(
            screen_frame.x + (#windows - index) * 40, -- x
            screen_frame.y + (index - 1) * 40, -- y
            math.min(win_frame.w, screen_frame.w - ((#windows - index) * 40)),
        math.min(win_frame.h, screen_frame.h - menubar_offset - ((index - 1) * 40))),
        nil
    }
    return win_pos
end

function cascade_windows()
    local screen = hs.window.focusedWindow():screen()
    
    windows = get_screen_windows(hs.window.visibleWindows(), screen)
    
    -- Set the coordinates and dimensions of each window
    local layout = {}
    for index, win in ipairs(windows) do
        layout[#layout + 1] = get_window_position(win, index)
    end
    
    -- Apply the layout
    hs.layout.apply(layout)
end

hs.hotkey.bind({'cmd', 'alt', 'ctrl'}, '/', cascade_windows)
