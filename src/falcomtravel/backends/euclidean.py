"""Euclidean / haversine backend — sanity baseline.

Useful as a fast lower bound or for small synthetic grids where the
Cartesian distance is a defensible proxy. Not a router. Do not use for
research conclusions about real-world travel time.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Hashable

from ..matrix import TravelMatrix
from ..modes import Mode

# Average speeds in m/s for converting straight-line distance to a time.
_DEFAULT_SPEED_MPS = {
    Mode.DRIVE: 13.4,         # ~30 mph urban
    Mode.WALK: 1.4,           # 5 km/h
    Mode.BIKE: 4.2,           # 15 km/h
    Mode.TRANSIT: 6.0,        # rough urban average including waits
    Mode.DRIVE_TRANSIT: 8.0,  # rough park-and-ride average
}


class EuclideanBackend:
    """Straight-line distance / speed.

    :param coords: ``{node_id: (x, y)}`` mapping. If ``geodesic=True``,
        coordinates must be ``(lon, lat)`` in degrees and times are computed
        via the haversine formula. If ``geodesic=False``, coordinates are
        treated as planar in metres (Euclidean distance).
    :param geodesic: Whether the coordinates are lon/lat (default True).
    :param speed_mps: Override the default speed table.
    """

    name = "euclidean"

    def __init__(
        self,
        coords: dict[Hashable, tuple[float, float]],
        *,
        geodesic: bool = True,
        speed_mps: dict[Mode, float] | None = None,
    ):
        self.coords = coords
        self.geodesic = geodesic
        self.speed_mps = {**_DEFAULT_SPEED_MPS, **(speed_mps or {})}

    def supports(self, mode: Mode) -> bool:
        return Mode.parse(mode) in self.speed_mps

    def compute(
        self,
        origins: Iterable[Hashable],
        destinations: Iterable[Hashable],
        mode: Mode,
        *,
        speed_mps: float | None = None,
    ) -> TravelMatrix:
        mode = Mode.parse(mode)
        speed = speed_mps if speed_mps is not None else self.speed_mps[mode]
        coords = self.coords

        data: dict[tuple, float] = {}
        unreachable: set[tuple] = set()
        dest_list = list(destinations)

        for o in origins:
            if o not in coords:
                for d in dest_list:
                    unreachable.add((o, d))
                continue
            ox, oy = coords[o]
            for d in dest_list:
                if d not in coords:
                    unreachable.add((o, d))
                    continue
                dx, dy = coords[d]
                meters = (
                    _haversine(ox, oy, dx, dy)
                    if self.geodesic
                    else math.hypot(ox - dx, oy - dy)
                )
                data[(o, d)] = meters / speed

        return TravelMatrix(
            data=data,
            mode=mode,
            meta={"backend": self.name, "speed_mps": speed, "geodesic": self.geodesic},
            unreachable=unreachable,
        )


def _haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Great-circle distance in metres."""
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
