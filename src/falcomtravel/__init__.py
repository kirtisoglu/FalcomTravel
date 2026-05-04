"""FalcomTravel — travel-time matrix computation for FalcomChain.

Public API:
    Mode               Mode enum (DRIVE, WALK, BIKE, TRANSIT, DRIVE_TRANSIT).
    TravelMatrix       Container around the (origin, dest) -> seconds dict.
    Backend            Protocol every backend implements.
    compute            Convenience: pick a backend by name, return a TravelMatrix.
    diagnose           Pre-flight check for disconnected nodes / unreachable OD pairs.

    GraphBackend       Dijkstra on a NetworkX graph with weighted edges.
    R5RBackend         Wraps r5r::travel_time_matrix via Rscript.
    EuclideanBackend   Haversine baseline.
"""

from .backends import (
    Backend,
    EuclideanBackend,
    GraphBackend,
    OSMnxBackend,
    R5RBackend,
)
from .compute import compute
from .diagnose import DiagnoseReport, diagnose
from .helpers import coords_from_graph
from .matrix import TravelMatrix
from .modes import Mode

__all__ = [
    "Mode",
    "TravelMatrix",
    "Backend",
    "GraphBackend",
    "R5RBackend",
    "OSMnxBackend",
    "EuclideanBackend",
    "compute",
    "diagnose",
    "DiagnoseReport",
    "coords_from_graph",
]

__version__ = "0.1.0"
