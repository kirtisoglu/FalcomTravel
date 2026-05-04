"""Graph backend — Dijkstra on a NetworkX graph.

Use this when you already have a graph with edge weights that encode
travel time (or any additive cost). It is the simplest backend, has no
external dependencies, and is the right choice for synthetic grids and
small custom networks.

Migrated from the legacy ``travel_time/traveltime.py``.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable
from typing import Hashable

from ..matrix import TravelMatrix
from ..modes import Mode


class GraphBackend:
    """Dijkstra single-source shortest path, batched over origins.

    :param graph: A ``networkx.Graph`` (or DiGraph). Edges must carry a
        numeric attribute used as the cost.
    :param weight: Edge attribute name. Default ``"time"`` matches the
        legacy convention; for ambulance / driving applications use
        ``"drive_time"`` or ``"length"`` (in seconds) depending on how
        you've encoded the graph.

    Mode is informational only here — the graph's edge weights determine
    what mode is actually being computed. Passing ``Mode.DRIVE`` against a
    walk-weighted graph is your problem, not ours.
    """

    name = "graph"

    def __init__(self, graph, weight: str = "time"):
        self.graph = graph
        self.weight = weight

    def supports(self, mode: Mode) -> bool:
        # Graph backend doesn't know what mode the edge weights represent.
        # Accept any mode and trust the caller.
        return True

    def compute(
        self,
        origins: Iterable[Hashable],
        destinations: Iterable[Hashable],
        mode: Mode,
        *,
        weight: str | None = None,
    ) -> TravelMatrix:
        graph = self.graph
        attr = weight or self.weight
        dest_set = set(destinations)

        data: dict[tuple, float] = {}
        unreachable: set[tuple] = set()

        for origin in origins:
            distances = _dijkstra(graph, origin, attr)
            for d in dest_set:
                t = distances.get(d, float("inf"))
                if t == float("inf"):
                    unreachable.add((origin, d))
                else:
                    data[(origin, d)] = t

        return TravelMatrix(
            data=data,
            mode=Mode.parse(mode),
            meta={"backend": self.name, "weight": attr},
            unreachable=unreachable,
        )


def _dijkstra(graph, source: Hashable, weight: str) -> dict[Hashable, float]:
    """Single-source shortest path. Inlined to avoid a NetworkX dependency
    on the lazy edge-attribute access pattern, and to keep behaviour
    identical to the legacy ``travel_time_to_source``."""
    dist: dict[Hashable, float] = {n: float("inf") for n in graph.nodes}
    dist[source] = 0.0
    pq: list[tuple[float, Hashable]] = [(0.0, source)]

    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, edata in graph[u].items():
            cost = edata[weight]
            nd = d + cost
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(pq, (nd, v))

    return dist
