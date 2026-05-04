"""Pre-flight diagnostics for travel-time computations.

The most common failure mode in real-world routing is **disconnected
network components**: r5r and OSRM will silently drop OD pairs whose
endpoints can't reach each other through the underlying street graph.
By the time the user sees a 5,496-pair gap in their matrix, it is hard
to tell whether the cause is OSM topology, GTFS coverage, or a snap
distance threshold.

This module surfaces the diagnostic up front:

>>> from falcomtravel import diagnose
>>> report = diagnose(graph, origins, destinations)
>>> if not report.ok:
...     print(report.summary())
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Hashable

import networkx as nx


@dataclass
class DiagnoseReport:
    """Result of a pre-flight diagnostic.

    :param n_components: Number of connected components in the input graph.
    :param component_sizes: Sorted list of component sizes, descending.
    :param disconnected_origins: Origins whose component is not the
        largest one. These are typically the origins that produce empty
        rows in r5r/OSRM output.
    :param disconnected_destinations: Same, for destinations.
    :param origin_components: ``{origin: component_index}`` (0 = largest).
    :param destination_components: Same shape, for destinations.
    :param missing_origins: Origins not present in the graph at all.
    :param missing_destinations: Same, for destinations.
    :param unreachable_pairs: Estimated count of OD pairs whose origin
        and destination land in different components — these will not be
        routable on this graph regardless of mode.
    """

    n_components: int = 0
    component_sizes: list[int] = field(default_factory=list)
    disconnected_origins: set[Hashable] = field(default_factory=set)
    disconnected_destinations: set[Hashable] = field(default_factory=set)
    origin_components: dict[Hashable, int] = field(default_factory=dict)
    destination_components: dict[Hashable, int] = field(default_factory=dict)
    missing_origins: set[Hashable] = field(default_factory=set)
    missing_destinations: set[Hashable] = field(default_factory=set)
    unreachable_pairs: int = 0

    @property
    def ok(self) -> bool:
        """True iff there are no missing nodes and no cross-component pairs."""
        return (
            not self.missing_origins
            and not self.missing_destinations
            and self.unreachable_pairs == 0
        )

    def summary(self) -> str:
        lines = []
        lines.append(f"Connected components: {self.n_components}")
        if self.n_components > 1:
            top = self.component_sizes[:5]
            lines.append(f"  sizes (top 5): {top}")
        if self.missing_origins:
            sample = list(self.missing_origins)[:5]
            lines.append(
                f"Missing origins (not in graph): {len(self.missing_origins)} "
                f"(e.g. {sample})"
            )
        if self.missing_destinations:
            sample = list(self.missing_destinations)[:5]
            lines.append(
                f"Missing destinations (not in graph): {len(self.missing_destinations)} "
                f"(e.g. {sample})"
            )
        if self.disconnected_origins:
            sample = list(self.disconnected_origins)[:5]
            lines.append(
                f"Origins outside main component: {len(self.disconnected_origins)} "
                f"(e.g. {sample})"
            )
        if self.disconnected_destinations:
            sample = list(self.disconnected_destinations)[:5]
            lines.append(
                f"Destinations outside main component: {len(self.disconnected_destinations)} "
                f"(e.g. {sample})"
            )
        if self.unreachable_pairs:
            lines.append(
                f"Cross-component OD pairs (will be unreachable): {self.unreachable_pairs}"
            )
        if self.ok:
            lines.append("OK — every origin and destination is in the same component.")
        return "\n".join(lines)


def diagnose(
    graph: nx.Graph,
    origins: Iterable[Hashable],
    destinations: Iterable[Hashable],
) -> DiagnoseReport:
    """Run a pre-flight check against a NetworkX graph.

    The graph should be the underlying network the routing engine will
    use — typically the street graph (e.g. from OSMnx) for driving/walking,
    or the cell-adjacency graph for synthetic grids. r5r-style backends
    don't expose their internal graph, so the closest practical check is
    to run this against the OSMnx ``graph_from_*`` build of the same OSM
    extract that r5r consumes.

    Topology check uses **weak connectivity** (treats edges as undirected)
    because r5r and most routing engines build undirected reachability
    when access mode is symmetric. If you have a strongly directional
    network (e.g. one-way driving with no walk fallback), prefer
    :func:`networkx.strongly_connected_components` and adapt this code.

    :param graph: The underlying network.
    :param origins: Origin node IDs.
    :param destinations: Destination node IDs.
    :returns: A :class:`DiagnoseReport`.
    """
    origins = list(origins)
    destinations = list(destinations)
    nodes = set(graph.nodes)

    missing_o = {o for o in origins if o not in nodes}
    missing_d = {d for d in destinations if d not in nodes}

    if graph.is_directed():
        components = list(nx.weakly_connected_components(graph))
    else:
        components = list(nx.connected_components(graph))
    components.sort(key=len, reverse=True)
    sizes = [len(c) for c in components]

    node_to_comp: dict[Hashable, int] = {}
    for idx, comp in enumerate(components):
        for n in comp:
            node_to_comp[n] = idx

    o_comp = {o: node_to_comp[o] for o in origins if o in node_to_comp}
    d_comp = {d: node_to_comp[d] for d in destinations if d in node_to_comp}

    disconnected_o = {o for o, c in o_comp.items() if c != 0}
    disconnected_d = {d for d, c in d_comp.items() if c != 0}

    unreachable = 0
    if len(components) > 1 and o_comp and d_comp:
        for o, oc in o_comp.items():
            for d, dc in d_comp.items():
                if oc != dc:
                    unreachable += 1

    return DiagnoseReport(
        n_components=len(components),
        component_sizes=sizes,
        disconnected_origins=disconnected_o,
        disconnected_destinations=disconnected_d,
        origin_components=o_comp,
        destination_components=d_comp,
        missing_origins=missing_o,
        missing_destinations=missing_d,
        unreachable_pairs=unreachable,
    )
