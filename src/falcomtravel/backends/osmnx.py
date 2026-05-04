"""OSMnx backend — pure-Python driving / walking / biking times.

No R. No Java. No Docker. ``pip install osmnx scipy`` and you're done.

OSMnx fetches the OSM street graph for a place (or bbox, or radius around
a point) and annotates edges with travel times in seconds. We then run
:func:`scipy.sparse.csgraph.dijkstra` for multi-source SSSP in C —
roughly an order of magnitude faster than NetworkX's pure-Python loop,
and fast enough to handle thousands of origins on a city-sized network.

Limitations vs r5r:
    - Driving / walking / biking only. No multimodal transit.
    - Edge speeds are inferred from OSM ``maxspeed`` tags, falling back
      to graph-wide mean. Less accurate than r5r's GTFS-aware routing.

For an ambulance application — driving only, on a single street network
— this is exactly the right tool: fast, accurate enough, no toolchain.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Hashable

from ..matrix import TravelMatrix
from ..modes import Mode

_NETWORK_TYPE_MAP: dict[Mode, str] = {
    Mode.DRIVE: "drive",
    Mode.WALK: "walk",
    Mode.BIKE: "bike",
}


class OSMnxBackend:
    """Routing on an OSM street graph via OSMnx + scipy.

    Use :meth:`from_place`, :meth:`from_bbox`, or :meth:`from_point` to
    build one without manually fetching OSM data. Pass an already-loaded
    OSMnx graph to the constructor if you have one.

    :param graph: An OSMnx-style ``MultiDiGraph`` with ``x``, ``y`` node
        attributes (lon, lat) and ``travel_time`` (seconds) edge
        attribute. The ``from_*`` classmethods build this for you.
    :param coords: ``{user_node_id: (lon, lat)}`` for every potential
        origin and destination. Each gets snapped to the nearest OSM
        street-graph node at compute time.
    :param weight: Edge attribute used as cost. Default ``"travel_time"``.
    """

    name = "osmnx"

    def __init__(
        self,
        graph,
        coords: dict[Hashable, tuple[float, float]],
        *,
        weight: str = "travel_time",
    ):
        self.graph = graph
        self.coords = coords
        self.weight = weight
        self._csr = None
        self._csr_weight: str | None = None
        self._osm_node_to_idx: dict[Hashable, int] | None = None

    @classmethod
    def from_place(
        cls,
        place,
        coords: dict[Hashable, tuple[float, float]],
        *,
        network_type: str = "drive",
        default_speed_kmh: float = 30.0,
        weight: str = "travel_time",
    ) -> "OSMnxBackend":
        """Build a backend by querying OSMnx for a place name.

        :param place: Anything OSMnx accepts — a string like
            ``"Chicago, Illinois, USA"`` or a list of place strings.
        :param coords: ``{user_node_id: (lon, lat)}``.
        :param network_type: ``"drive"`` (default), ``"walk"``, ``"bike"``,
            or ``"all"``.
        :param default_speed_kmh: Fallback speed for OSM edges with no
            ``maxspeed`` tag. Default 30 km/h.
        """
        ox = _import_osmnx()
        graph = ox.graph_from_place(place, network_type=network_type)
        graph = _annotate_travel_times(ox, graph, default_speed_kmh)
        return cls(graph, coords, weight=weight)

    @classmethod
    def from_bbox(
        cls,
        bbox: tuple[float, float, float, float],
        coords: dict[Hashable, tuple[float, float]],
        *,
        network_type: str = "drive",
        default_speed_kmh: float = 30.0,
        weight: str = "travel_time",
    ) -> "OSMnxBackend":
        """Build a backend from a bounding box.

        :param bbox: ``(west, south, east, north)`` in degrees (OSMnx 2.x convention).
        """
        ox = _import_osmnx()
        graph = ox.graph_from_bbox(bbox=bbox, network_type=network_type)
        graph = _annotate_travel_times(ox, graph, default_speed_kmh)
        return cls(graph, coords, weight=weight)

    @classmethod
    def from_point(
        cls,
        point: tuple[float, float],
        coords: dict[Hashable, tuple[float, float]],
        *,
        dist: float = 10_000,
        network_type: str = "drive",
        default_speed_kmh: float = 30.0,
        weight: str = "travel_time",
    ) -> "OSMnxBackend":
        """Build a backend centered on a point.

        :param point: ``(lat, lon)`` in degrees.
        :param dist: Radius in metres (default 10 km).
        """
        ox = _import_osmnx()
        graph = ox.graph_from_point(point, dist=dist, network_type=network_type)
        graph = _annotate_travel_times(ox, graph, default_speed_kmh)
        return cls(graph, coords, weight=weight)

    def supports(self, mode: Mode) -> bool:
        return Mode.parse(mode) in _NETWORK_TYPE_MAP

    def snap(self, ids: Iterable[Hashable]) -> dict[Hashable, Hashable]:
        """Snap user node IDs to nearest OSM street-graph nodes.

        :returns: ``{user_id: osm_node_id}``.
        """
        ox = _import_osmnx()
        ids = list(ids)
        lons = [self.coords[i][0] for i in ids]
        lats = [self.coords[i][1] for i in ids]
        snapped = ox.distance.nearest_nodes(self.graph, X=lons, Y=lats)
        return dict(zip(ids, snapped))

    def compute(
        self,
        origins: Iterable[Hashable],
        destinations: Iterable[Hashable],
        mode: Mode,
        *,
        weight: str | None = None,
    ) -> TravelMatrix:
        """Compute the OD travel-time matrix.

        :param origins: User node IDs (must be in ``self.coords``).
        :param destinations: User node IDs (must be in ``self.coords``).
        :param mode: One of DRIVE, WALK, BIKE. Informational — the
            graph's ``network_type`` already determined the actual mode.
        :param weight: Override the edge attribute used as cost.
        :returns: A :class:`TravelMatrix` in **seconds**.
        """
        mode = Mode.parse(mode)
        if not self.supports(mode):
            raise ValueError(
                f"OSMnxBackend supports DRIVE/WALK/BIKE only; got {mode}. "
                f"For transit, use R5RBackend."
            )
        attr = weight or self.weight

        origins = list(origins)
        destinations = list(destinations)
        self._check_coords(origins, "origin")
        self._check_coords(destinations, "destination")

        snap_o = self.snap(origins)
        snap_d = self.snap(destinations)

        csr, node_idx = self._adjacency(attr)

        import numpy as np
        from scipy.sparse.csgraph import dijkstra

        origin_indices = np.fromiter(
            (node_idx[snap_o[o]] for o in origins),
            dtype=np.int64,
            count=len(origins),
        )
        dest_indices = np.fromiter(
            (node_idx[snap_d[d]] for d in destinations),
            dtype=np.int64,
            count=len(destinations),
        )

        dist_matrix = dijkstra(csr, indices=origin_indices, directed=True)

        # dist_matrix[i, j] = distance from origins[i] to OSM-node-index j.
        # Slice out the destination columns in one numpy op.
        sub = dist_matrix[:, dest_indices]

        data: dict[tuple, float] = {}
        unreachable: set[tuple] = set()
        finite_mask = np.isfinite(sub)
        for i, o in enumerate(origins):
            for j, d in enumerate(destinations):
                if finite_mask[i, j]:
                    data[(o, d)] = float(sub[i, j])
                else:
                    unreachable.add((o, d))

        return TravelMatrix(
            data=data,
            mode=mode,
            meta={
                "backend": self.name,
                "weight": attr,
                "time_unit": "seconds",
                "n_osm_nodes": len(node_idx),
                "n_osm_edges": int(csr.nnz),
            },
            unreachable=unreachable,
        )

    def _check_coords(self, ids: list, label: str) -> None:
        missing = [i for i in ids if i not in self.coords]
        if missing:
            sample = missing[:5]
            raise KeyError(
                f"{len(missing)} {label} IDs missing from coords (e.g. {sample}). "
                f"Every origin and destination must have a (lon, lat) entry."
            )

    def _adjacency(self, weight: str):
        """Build (and cache) a CSR adjacency matrix keyed by ``weight``.

        Handles MultiDiGraph parallel edges by keeping the minimum weight.
        """
        if self._csr is not None and self._csr_weight == weight:
            return self._csr, self._osm_node_to_idx  # type: ignore[return-value]

        import numpy as np
        from scipy.sparse import csr_matrix

        nodes = list(self.graph.nodes)
        node_idx = {n: i for i, n in enumerate(nodes)}
        n = len(nodes)

        min_weight: dict[tuple, float] = {}
        edges_iter = (
            self.graph.edges(keys=True, data=True)
            if self.graph.is_multigraph()
            else self.graph.edges(data=True)
        )
        for item in edges_iter:
            if self.graph.is_multigraph():
                u, v, _k, edata = item
            else:
                u, v, edata = item
            if weight not in edata:
                continue
            w = float(edata[weight])
            key = (u, v)
            cur = min_weight.get(key)
            if cur is None or w < cur:
                min_weight[key] = w

        if not min_weight:
            raise ValueError(
                f"No edges in the graph carry the {weight!r} attribute. "
                f"Did you forget add_edge_speeds + add_edge_travel_times?"
            )

        rows = np.fromiter((node_idx[u] for (u, _v) in min_weight), dtype=np.int64, count=len(min_weight))
        cols = np.fromiter((node_idx[v] for (_u, v) in min_weight), dtype=np.int64, count=len(min_weight))
        data = np.fromiter(min_weight.values(), dtype=np.float64, count=len(min_weight))

        csr = csr_matrix((data, (rows, cols)), shape=(n, n))
        self._csr = csr
        self._csr_weight = weight
        self._osm_node_to_idx = node_idx
        return csr, node_idx


def _import_osmnx():
    try:
        import osmnx
        return osmnx
    except ImportError as e:
        raise ImportError(
            "OSMnxBackend requires osmnx and scipy. Install with: "
            'pip install "falcomtravel[osmnx]"'
        ) from e


def _annotate_travel_times(ox: Any, graph, default_speed_kmh: float):
    """Add ``speed_kph`` and ``travel_time`` (seconds) edge attrs in place."""
    try:
        graph = ox.add_edge_speeds(graph, fallback=default_speed_kmh)
    except TypeError:
        graph = ox.add_edge_speeds(graph)
    graph = ox.add_edge_travel_times(graph)
    return graph
