"""Backend protocol — the contract every routing engine adapter implements."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Hashable, Protocol, runtime_checkable

from ..matrix import TravelMatrix
from ..modes import Mode


@runtime_checkable
class Backend(Protocol):
    """A travel-time backend.

    Implementations may be in-process (NetworkX Dijkstra), HTTP clients
    (OSRM, Valhalla), or shellouts (r5r via Rscript). All return a
    :class:`TravelMatrix` keyed by the same node IDs the caller passed in.
    """

    name: str

    def supports(self, mode: Mode) -> bool:
        """Return True if this backend can compute travel times in ``mode``."""
        ...

    def compute(
        self,
        origins: Iterable[Hashable],
        destinations: Iterable[Hashable],
        mode: Mode,
        **kwargs,
    ) -> TravelMatrix:
        """Compute the OD travel-time matrix.

        :param origins: Origin node IDs.
        :param destinations: Destination node IDs.
        :param mode: Travel mode.
        :param kwargs: Backend-specific options (e.g. ``departure_time`` for
            r5r, ``max_trip_duration`` to cap query cost, etc.).
        :returns: A :class:`TravelMatrix` whose keys are exactly the
            ``(origin, destination)`` pairs that produced a finite time.
            Pairs that the engine could not route appear in
            ``matrix.unreachable`` rather than ``matrix.data``.
        """
        ...
