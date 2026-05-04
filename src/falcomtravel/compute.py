"""``compute()`` — pick a backend, return a TravelMatrix.

This is a thin convenience over the explicit ``Backend`` constructors.
For real work you'll usually instantiate a backend directly so you can
hold its config (graph, coords, network data path) across calls.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Hashable

from .backends import Backend, EuclideanBackend, GraphBackend, OSMnxBackend, R5RBackend
from .matrix import TravelMatrix
from .modes import Mode


def compute(
    backend: str | Backend,
    *,
    origins: Iterable[Hashable],
    destinations: Iterable[Hashable],
    mode: Mode | str = Mode.DRIVE,
    **kwargs: Any,
) -> TravelMatrix:
    """Compute a travel-time matrix.

    :param backend: Either a ready-made :class:`Backend` instance, or one
        of the string aliases ``"graph"``, ``"r5r"``, ``"euclidean"``.
        When passing a string, you must supply the backend's required
        constructor args via ``kwargs`` (``graph=`` for ``"graph"``,
        ``data_path=`` and ``coords=`` for ``"r5r"``, ``coords=`` for
        ``"euclidean"``). Per-call options are passed through.
    :param origins: Origin node IDs.
    :param destinations: Destination node IDs.
    :param mode: Travel mode.
    :returns: A :class:`TravelMatrix`.
    """
    mode = Mode.parse(mode)
    if isinstance(backend, str):
        backend = _build(backend, kwargs)
    return backend.compute(origins, destinations, mode, **kwargs)


def _build(name: str, kwargs: dict[str, Any]) -> Backend:
    """Pop construction args out of kwargs, leaving per-call args behind."""
    if name == "graph":
        graph = kwargs.pop("graph")
        weight = kwargs.pop("weight", "time")
        return GraphBackend(graph=graph, weight=weight)
    if name == "r5r":
        return R5RBackend(
            data_path=kwargs.pop("data_path"),
            coords=kwargs.pop("coords"),
            timezone=kwargs.pop("timezone", "UTC"),
            r_script=kwargs.pop("r_script", None),
            rscript_bin=kwargs.pop("rscript_bin", "Rscript"),
        )
    if name == "euclidean":
        return EuclideanBackend(
            coords=kwargs.pop("coords"),
            geodesic=kwargs.pop("geodesic", True),
            speed_mps=kwargs.pop("speed_mps", None),
        )
    if name == "osmnx":
        graph = kwargs.pop("graph", None)
        coords = kwargs.pop("coords")
        weight = kwargs.pop("weight", "travel_time")
        if graph is not None:
            return OSMnxBackend(graph=graph, coords=coords, weight=weight)
        # Place / bbox / point shortcut.
        if "place" in kwargs:
            return OSMnxBackend.from_place(
                kwargs.pop("place"),
                coords,
                network_type=kwargs.pop("network_type", "drive"),
                default_speed_kmh=kwargs.pop("default_speed_kmh", 30.0),
                weight=weight,
            )
        if "bbox" in kwargs:
            return OSMnxBackend.from_bbox(
                kwargs.pop("bbox"),
                coords,
                network_type=kwargs.pop("network_type", "drive"),
                default_speed_kmh=kwargs.pop("default_speed_kmh", 30.0),
                weight=weight,
            )
        if "point" in kwargs:
            return OSMnxBackend.from_point(
                kwargs.pop("point"),
                coords,
                dist=kwargs.pop("dist", 10_000),
                network_type=kwargs.pop("network_type", "drive"),
                default_speed_kmh=kwargs.pop("default_speed_kmh", 30.0),
                weight=weight,
            )
        raise ValueError(
            "osmnx backend needs one of: graph=, place=, bbox=, or point=."
        )
    raise ValueError(f"unknown backend {name!r}; valid: graph, r5r, osmnx, euclidean")
