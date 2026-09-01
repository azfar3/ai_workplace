"""
Geodesic distance helpers for attendance geofencing.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in meters between two WGS84 coordinates."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_M * c


def is_within_radius(
    employee_lat: float,
    employee_lon: float,
    center_lat: float,
    center_lon: float,
    radius_m: float,
) -> tuple[bool, float]:
    """Return (inside, distance_m)."""
    distance_m = haversine_distance_m(employee_lat, employee_lon, center_lat, center_lon)
    return distance_m <= radius_m, distance_m
