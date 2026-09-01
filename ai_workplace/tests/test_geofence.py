"""
Unit tests for geofence distance calculations.
"""

from __future__ import annotations

import unittest

from ai_workplace.utils.geofence import haversine_distance_m, is_within_radius


class TestGeofence(unittest.TestCase):
    def test_same_point_zero_distance(self):
        self.assertAlmostEqual(haversine_distance_m(33.6844, 73.0479, 33.6844, 73.0479), 0.0, places=1)

    def test_within_radius(self):
        inside, dist = is_within_radius(33.6844, 73.0479, 33.6845, 73.0480, 200)
        self.assertTrue(inside)
        self.assertLess(dist, 200)

    def test_outside_radius(self):
        inside, dist = is_within_radius(33.6844, 73.0479, 33.7000, 73.1000, 200)
        self.assertFalse(inside)
        self.assertGreater(dist, 200)


if __name__ == "__main__":
    unittest.main()
