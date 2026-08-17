#!/usr/bin/env python3
"""Unit tests for the cascade geometry. No X server required.

    python3 linux/test_cascade.py
"""

import unittest

from three_finger_slash import STEP, Rect, get_window_position


class GetWindowPositionTest(unittest.TestCase):
    # A 1920x1080 screen with a 30px panel already excluded by _NET_WORKAREA.
    SCREEN = Rect(0, 30, 1920, 1050)

    def position(self, index, count, win=Rect(0, 0, 800, 600), screen=None):
        return get_window_position(win, index, count, screen or self.SCREEN, 0)

    def test_single_window_fills_top_left_of_work_area(self):
        pos = self.position(1, 1)
        self.assertEqual(pos, Rect(0, 30, 800, 600))

    def test_front_window_is_flush_left(self):
        """Index == count is the focused window: no x offset, so titles stay visible."""
        for count in (1, 3, 5):
            with self.subTest(count=count):
                self.assertEqual(self.position(count, count).x, self.SCREEN.x)

    def test_offsets_match_the_hammerspoon_formula(self):
        """Same reverse cascade as get_window_position in ../macos/init.lua."""
        count = 5
        for index in range(1, count + 1):
            with self.subTest(index=index):
                pos = self.position(index, count)
                self.assertEqual(pos.x, self.SCREEN.x + (count - index) * STEP)
                self.assertEqual(pos.y, self.SCREEN.y + (index - 1) * STEP)

    def test_x_offset_decreases_and_y_increases_with_index(self):
        count = 4
        positions = [self.position(i, count) for i in range(1, count + 1)]
        xs = [p.x for p in positions]
        ys = [p.y for p in positions]
        self.assertEqual(xs, sorted(xs, reverse=True))
        self.assertEqual(ys, sorted(ys))

    def test_small_window_keeps_its_own_size(self):
        pos = self.position(2, 3, win=Rect(0, 0, 640, 480))
        self.assertEqual((pos.w, pos.h), (640, 480))

    def test_oversized_window_is_clamped_to_remaining_space(self):
        huge = Rect(0, 0, 5000, 5000)
        count = 3
        for index in range(1, count + 1):
            with self.subTest(index=index):
                pos = self.position(index, count, win=huge)
                self.assertEqual(pos.w, self.SCREEN.w - (count - index) * STEP)
                self.assertEqual(pos.h, self.SCREEN.h - (index - 1) * STEP)

    def test_clamped_window_stays_within_the_work_area(self):
        huge = Rect(0, 0, 5000, 5000)
        count = 6
        for index in range(1, count + 1):
            with self.subTest(index=index):
                pos = self.position(index, count, win=huge)
                self.assertLessEqual(pos.x + pos.w, self.SCREEN.x + self.SCREEN.w)
                self.assertLessEqual(pos.y + pos.h, self.SCREEN.y + self.SCREEN.h)

    def test_panel_offset_reduces_available_height(self):
        win = Rect(0, 0, 5000, 5000)
        without = get_window_position(win, 1, 1, self.SCREEN, 0)
        with_offset = get_window_position(win, 1, 1, self.SCREEN, 14)
        self.assertEqual(without.h - with_offset.h, 14)

    def test_offsets_are_relative_to_a_non_zero_screen_origin(self):
        """Second monitor: the cascade is anchored to that monitor, not to 0,0."""
        screen = Rect(1920, 0, 1280, 1024)
        pos = self.position(1, 3, screen=screen)
        self.assertEqual(pos.x, 1920 + 2 * STEP)
        self.assertEqual(pos.y, 0)


class RectTest(unittest.TestCase):
    def test_intersect_returns_overlap(self):
        self.assertEqual(Rect(0, 0, 100, 100).intersect(Rect(50, 50, 100, 100)), Rect(50, 50, 50, 50))

    def test_intersect_returns_none_when_disjoint(self):
        """Drives the fallback for a _NET_WORKAREA that omits a second monitor."""
        self.assertIsNone(Rect(0, 0, 100, 100).intersect(Rect(200, 200, 50, 50)))

    def test_contains_uses_half_open_bounds(self):
        rect = Rect(10, 10, 100, 100)
        self.assertTrue(rect.contains((10, 10)))
        self.assertTrue(rect.contains((109, 109)))
        self.assertFalse(rect.contains((110, 110)))

    def test_center(self):
        self.assertEqual(Rect(0, 0, 800, 600).center, (400, 300))


if __name__ == "__main__":
    unittest.main(verbosity=2)
