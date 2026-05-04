"""Backend implementations.

Each backend computes a travel-time matrix between two sets of points,
returning a :class:`TravelMatrix`. Backends share the :class:`Backend`
protocol and translate the unified :class:`Mode` enum into their own
native vocabulary.
"""

from .base import Backend
from .euclidean import EuclideanBackend
from .graph import GraphBackend
from .osmnx import OSMnxBackend
from .r5r import R5RBackend

__all__ = [
    "Backend",
    "GraphBackend",
    "R5RBackend",
    "OSMnxBackend",
    "EuclideanBackend",
]
