"""Small helpers that turn common inputs into the shapes backends expect.

Keep these dependency-free — they're meant to be cheap glue, not analysis.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Hashable


def coords_from_graph(
    graph,
    *,
    x: str = "x",
    y: str = "y",
    nodes: Iterable[Hashable] | None = None,
) -> dict[Hashable, tuple[float, float]]:
    """Extract a ``{node_id: (lon, lat)}`` dict from a NetworkX graph.

    Reads ``(x, y)`` node attributes and packages them as the ``coords``
    dict that :class:`R5RBackend` and :class:`OSMnxBackend` expect.

    :param graph: A NetworkX graph with per-node coordinate attributes.
    :param x: Attribute name holding the longitude. Default ``"x"``;
        FalcomChain graphs use ``"C_X"``; OSMnx uses ``"x"``.
    :param y: Attribute name holding the latitude. Default ``"y"``;
        FalcomChain uses ``"C_Y"``.
    :param nodes: Optional subset of nodes. Default: all nodes in the graph.
    :raises KeyError: if any selected node is missing the coord attribute.
    :returns: ``{node: (lon, lat)}``.

    Example::

        # FalcomChain block-level graph
        coords = coords_from_graph(graph, x="C_X", y="C_Y")

        # OSMnx street graph
        coords = coords_from_graph(G)  # defaults to x, y
    """
    if nodes is None:
        nodes = graph.nodes
    out: dict[Hashable, tuple[float, float]] = {}
    for n in nodes:
        attrs = graph.nodes[n]
        try:
            out[n] = (float(attrs[x]), float(attrs[y]))
        except KeyError as e:
            raise KeyError(
                f"node {n!r} is missing coordinate attribute {e.args[0]!r}; "
                f"pass x=/y= to point at the right attribute names"
            ) from e
    return out
