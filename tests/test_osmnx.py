"""OSMnxBackend tests using a synthetic OSMnx-style graph.

Skips automatically if osmnx + scipy aren't installed. Does not hit
the network — we hand-build a tiny MultiDiGraph that looks like
something OSMnx would produce.
"""

from __future__ import annotations

import pytest

osmnx = pytest.importorskip("osmnx")
scipy = pytest.importorskip("scipy")

import networkx as nx

import falcomtravel as ft


def _toy_osmnx_graph():
    """A 4-node directed grid with travel_time edges, mimicking osmnx output.

    Layout (lon, lat in degrees, roughly Chicago-ish):

        n10 (-87.70, 41.80) ── 60s ──> n11 (-87.69, 41.80)
                                        │
                                        60s
                                        │
                                        v
        n20 (-87.70, 41.79) <── 60s ── n21 (-87.69, 41.79)
    """
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    G.add_node(10, x=-87.70, y=41.80)
    G.add_node(11, x=-87.69, y=41.80)
    G.add_node(20, x=-87.70, y=41.79)
    G.add_node(21, x=-87.69, y=41.79)
    # bidirectional outer ring + one diagonal cut
    for u, v in [(10, 11), (11, 21), (21, 20), (20, 10)]:
        G.add_edge(u, v, key=0, length=1000.0, travel_time=60.0)
        G.add_edge(v, u, key=0, length=1000.0, travel_time=60.0)
    return G


def test_compute_basic():
    G = _toy_osmnx_graph()
    coords = {
        "A": (-87.70, 41.80),  # near n10
        "B": (-87.69, 41.79),  # near n21
    }
    backend = ft.OSMnxBackend(G, coords)
    matrix = backend.compute(origins=["A"], destinations=["A", "B"], mode=ft.Mode.DRIVE)

    assert ("A", "A") in matrix.data
    assert matrix[("A", "A")] == 0.0
    # A->B is two hops of 60s either through n11 or n20
    assert matrix[("A", "B")] == 120.0
    assert matrix.meta["time_unit"] == "seconds"
    assert matrix.meta["backend"] == "osmnx"


def test_supports_modes():
    G = _toy_osmnx_graph()
    b = ft.OSMnxBackend(G, coords={})
    assert b.supports(ft.Mode.DRIVE)
    assert b.supports(ft.Mode.WALK)
    assert b.supports(ft.Mode.BIKE)
    assert not b.supports(ft.Mode.TRANSIT)


def test_compute_rejects_transit():
    G = _toy_osmnx_graph()
    backend = ft.OSMnxBackend(G, coords={"A": (-87.70, 41.80)})
    with pytest.raises(ValueError, match="DRIVE/WALK/BIKE only"):
        backend.compute(origins=["A"], destinations=["A"], mode=ft.Mode.TRANSIT)


def test_compute_missing_coord():
    G = _toy_osmnx_graph()
    backend = ft.OSMnxBackend(G, coords={"A": (-87.70, 41.80)})
    with pytest.raises(KeyError, match="missing from coords"):
        backend.compute(origins=["A"], destinations=["NOPE"], mode=ft.Mode.DRIVE)


def test_no_travel_time_attribute():
    """Construction is fine; compute fails clearly when edges lack ``travel_time``."""
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    G.add_node(1, x=0.0, y=0.0)
    G.add_node(2, x=0.01, y=0.0)
    G.add_edge(1, 2, key=0, length=1000.0)  # no travel_time
    backend = ft.OSMnxBackend(G, coords={"A": (0.0, 0.0), "B": (0.01, 0.0)})
    with pytest.raises(ValueError, match="travel_time"):
        backend.compute(origins=["A"], destinations=["B"], mode=ft.Mode.DRIVE)


def test_unreachable_across_components():
    """Two disconnected sub-grids: cross-component pairs are unreachable."""
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    G.add_node(1, x=0.0, y=0.0)
    G.add_node(2, x=0.01, y=0.0)
    G.add_node(99, x=10.0, y=10.0)  # far away, no edges
    G.add_edge(1, 2, key=0, length=1000.0, travel_time=60.0)
    G.add_edge(2, 1, key=0, length=1000.0, travel_time=60.0)

    coords = {"A": (0.0, 0.0), "B": (0.01, 0.0), "Far": (10.0, 10.0)}
    backend = ft.OSMnxBackend(G, coords)
    matrix = backend.compute(origins=["A"], destinations=["B", "Far"], mode=ft.Mode.DRIVE)

    assert ("A", "B") in matrix.data
    assert ("A", "Far") in matrix.unreachable


def test_coords_from_graph():
    G = nx.Graph()
    G.add_node(1, C_X=-87.7, C_Y=41.8, population=100)
    G.add_node(2, C_X=-87.6, C_Y=41.7, population=200)
    coords = ft.coords_from_graph(G, x="C_X", y="C_Y")
    assert coords == {1: (-87.7, 41.8), 2: (-87.6, 41.7)}


def test_coords_from_graph_default_attrs():
    """OSMnx graphs use 'x' and 'y' — that's the helper's default."""
    G = nx.Graph()
    G.add_node(1, x=10.0, y=20.0)
    G.add_node(2, x=30.0, y=40.0)
    coords = ft.coords_from_graph(G)
    assert coords == {1: (10.0, 20.0), 2: (30.0, 40.0)}


def test_coords_from_graph_subset():
    G = nx.Graph()
    G.add_node(1, C_X=1.0, C_Y=1.0)
    G.add_node(2, C_X=2.0, C_Y=2.0)
    G.add_node(3, C_X=3.0, C_Y=3.0)
    coords = ft.coords_from_graph(G, x="C_X", y="C_Y", nodes=[1, 3])
    assert set(coords) == {1, 3}


def test_coords_from_graph_missing_attr():
    G = nx.Graph()
    G.add_node(1, x=1.0)  # no y
    with pytest.raises(KeyError, match="missing coordinate attribute"):
        ft.coords_from_graph(G)


def test_compute_string_alias():
    G = _toy_osmnx_graph()
    coords = {"A": (-87.70, 41.80), "B": (-87.69, 41.79)}
    matrix = ft.compute(
        "osmnx",
        graph=G,
        coords=coords,
        origins=["A"],
        destinations=["B"],
        mode="drive",
    )
    assert matrix[("A", "B")] == 120.0
