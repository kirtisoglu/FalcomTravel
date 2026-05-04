"""Smoke tests — exercise the public API on small inputs that don't need
external services (no R, no GTFS, no internet).
"""

import networkx as nx
import pytest

import falcomtravel as ft


def test_mode_parse():
    assert ft.Mode.parse("drive") is ft.Mode.DRIVE
    assert ft.Mode.parse(ft.Mode.WALK) is ft.Mode.WALK
    with pytest.raises(ValueError):
        ft.Mode.parse("teleport")


def test_travel_matrix_basics():
    m = ft.TravelMatrix.from_dict({(1, 2): 60.0, (1, 3): 120.0}, mode=ft.Mode.DRIVE)
    assert len(m) == 2
    assert m[(1, 2)] == 60.0
    assert (1, 2) in m
    assert m.origins() == {1}
    assert m.destinations() == {2, 3}


def test_travel_matrix_fill_missing():
    m = ft.TravelMatrix(data={(1, 2): 60.0})
    added = m.fill_missing(nodes=[2, 3, 4], candidates=[1, 5], value=0.0)
    assert added == 5  # (1,3), (1,4), (5,2), (5,3), (5,4)
    assert m[(5, 2)] == 0.0
    assert m[(1, 2)] == 60.0  # pre-existing not overwritten


def test_graph_backend_dijkstra():
    G = nx.path_graph(4)
    for u, v in G.edges:
        G[u][v]["time"] = 10.0
    backend = ft.GraphBackend(G, weight="time")
    matrix = backend.compute(origins=[0], destinations=[0, 1, 2, 3], mode=ft.Mode.DRIVE)
    assert matrix[(0, 3)] == 30.0
    assert matrix.unreachable == set()


def test_graph_backend_unreachable():
    G = nx.Graph()
    G.add_edge(0, 1, time=5.0)
    G.add_node(99)  # isolated
    backend = ft.GraphBackend(G)
    matrix = backend.compute(origins=[0], destinations=[1, 99], mode=ft.Mode.DRIVE)
    assert (0, 1) in matrix.data
    assert (0, 99) in matrix.unreachable


def test_euclidean_backend_geodesic():
    coords = {0: (-87.6, 41.8), 1: (-87.6, 41.81)}  # ~1.1 km apart in lat
    backend = ft.EuclideanBackend(coords, geodesic=True)
    matrix = backend.compute(origins=[0], destinations=[1], mode=ft.Mode.WALK)
    seconds = matrix[(0, 1)]
    assert 700 < seconds < 900  # ~1100m / 1.4 m/s = ~785s


def test_diagnose_two_components():
    G = nx.Graph()
    G.add_edges_from([(0, 1), (1, 2)])  # comp A
    G.add_edges_from([(3, 4)])           # comp B
    report = ft.diagnose(G, origins=[0, 3], destinations=[2, 4])
    assert report.n_components == 2
    assert report.disconnected_origins == {3}
    assert report.disconnected_destinations == {4}
    assert report.unreachable_pairs == 2  # (0,4) and (3,2)
    assert not report.ok


def test_diagnose_missing_nodes():
    G = nx.Graph()
    G.add_edges_from([(0, 1), (1, 2)])
    report = ft.diagnose(G, origins=[0, 99], destinations=[2])
    assert report.missing_origins == {99}
    assert report.ok is False


def test_diagnose_clean():
    G = nx.path_graph(5)
    report = ft.diagnose(G, origins=[0], destinations=[4])
    assert report.ok
    assert report.n_components == 1


def test_compute_convenience():
    G = nx.path_graph(3)
    for u, v in G.edges:
        G[u][v]["time"] = 7.0
    matrix = ft.compute(
        "graph",
        graph=G,
        origins=[0],
        destinations=[2],
        mode="drive",
    )
    assert matrix[(0, 2)] == 14.0


def test_backend_supports():
    assert ft.GraphBackend(nx.Graph()).supports(ft.Mode.DRIVE)
    assert ft.EuclideanBackend({}).supports(ft.Mode.DRIVE)
