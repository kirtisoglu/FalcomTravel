# FalcomTravel

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**FalcomTravel** computes travel-time matrices for facility-location and
districting workflows. It is a thin, multi-backend façade over existing
routing engines (`r5r`, OSRM, OSMnx, raw graph Dijkstra, Euclidean) that
returns the exact `Dict[(origin, destination), seconds]` shape that
[FalcomChain](https://github.com/kirtisoglu/FalcomChain)'s
`Assignment.travel_times` consumes.

> **Status:** Pre-publication, under active development. API may evolve.

---

## What it gives you

- **One output contract** — `(o, d) -> seconds` dict, regardless of backend.
- **One mode enum** — `DRIVE`, `WALK`, `BIKE`, `TRANSIT`, `DRIVE_TRANSIT`,
  translated per-backend.
- **Pre-flight diagnostics** — `diagnose()` reports disconnected
  components and cross-component OD pairs *before* you wait an hour for
  r5r to silently drop them.
- **Native FalcomChain interop** — drop the result straight into
  `Assignment.travel_times`.

What it does **not** do: re-implement routing. It wraps engines that are
already better at it than anything we could write.

---

## Installation

```bash
pip install -e .                  # core only
pip install -e ".[parquet]"       # to read r5r parquet output
pip install -e ".[osmnx,osrm]"    # extra backends
pip install -e ".[all]"           # everything
```

`r5r` requires R (4.0+), Java (21+), and the `r5r` R package — see the
[r5r install guide](https://ipeagit.github.io/r5r/articles/intro_to_r5r.html).

---

## Quick start

### Driving times — no R, no Java

```python
import falcomtravel as ft

# (lon, lat) for every node — typical: census-block centroids
coords = {1001: (-87.69, 41.78), 1002: (-87.70, 41.79), ...}

backend = ft.OSMnxBackend.from_place(
    "Chicago, Illinois, USA",
    coords=coords,
    network_type="drive",
)
matrix = backend.compute(
    origins=[1001, 1002, ...],
    destinations=list(coords),
    mode=ft.Mode.DRIVE,
)

# Hand the result to FalcomChain
from types import MappingProxyType
from falcomchain.partition import Assignment
Assignment.travel_times = MappingProxyType(matrix.as_dict())
```

Travel times are in **seconds**. OSMnx fetches the OSM driving network
on the fly; `scipy.sparse.csgraph.dijkstra` runs multi-source SSSP in C.

### Multimodal with transit (r5r)

When you need transit and GTFS-aware routing, use r5r:

```python
backend = ft.R5RBackend(
    data_path="data/chicago",       # OSM .pbf + GTFS .zip
    coords=coords,
    timezone="America/Chicago",
)
matrix = backend.compute(
    origins=[1001, 1002, ...],
    destinations=list(coords),
    mode=ft.Mode.TRANSIT,
    departure_time="2025-09-08 09:00:00",
    max_trip_duration=900,           # minutes
)
```

### Build coords from a NetworkX graph

If your nodes already carry coordinate attributes
(e.g. FalcomChain's ``C_X`` / ``C_Y``):

```python
coords = ft.coords_from_graph(graph, x="C_X", y="C_Y")
```

### Pre-flight diagnose: catch disconnected nodes early

```python
import osmnx as ox
import falcomtravel as ft

# Build the street graph that r5r will route on (driving network)
G = ox.graph_from_place("Chicago, Illinois, USA", network_type="drive")

report = ft.diagnose(G, origins=ambulance_bases, destinations=demand_nodes)
if not report.ok:
    print(report.summary())
    # Decide: drop disconnected nodes, snap to nearest reachable component,
    # or re-extract OSM with a wider boundary.
```

A real Chicago example finds 2 connected components, with 2 census
blocks (`30185`, `32588`) on isolated road fragments — these are the
nodes that produce the "5,496 missing OD pairs" you'd otherwise hit
silently inside r5r.

### Tiny synthetic graph (no external dependencies)

```python
import networkx as nx
import falcomtravel as ft

G = nx.grid_2d_graph(10, 10)
for u, v in G.edges:
    G[u][v]["time"] = 60.0     # 1 minute per edge

backend = ft.GraphBackend(G, weight="time")
matrix = backend.compute(
    origins=[(0, 0)],
    destinations=list(G.nodes),
    mode=ft.Mode.DRIVE,         # informational; weights determine actual mode
)
```

### Persist & reload large matrices

```python
matrix.to_parquet("output/ttm.parquet")

# Or load r5r's partitioned-by-from_id output directly:
matrix = ft.TravelMatrix.from_parquet(
    "output/ttm_parquet",        # r5r's write_dataset(partitioning="from_id")
    cast=int,                     # cast IDs back to ints
)
```

---

## Backends

| Backend            | Best for                                   | External deps              | Modes                                       |
| ------------------ | ------------------------------------------ | -------------------------- | ------------------------------------------- |
| `OSMnxBackend`     | Driving / walking / biking, no toolchain   | `osmnx`, `scipy` (pip)     | DRIVE, WALK, BIKE                           |
| `R5RBackend`       | Multimodal urban routing with GTFS         | R, Java, `r5r` R package   | DRIVE, WALK, BIKE, TRANSIT, DRIVE_TRANSIT   |
| `GraphBackend`     | Synthetic grids, custom weighted graphs    | none                       | any (caller's responsibility)               |
| `EuclideanBackend` | Sanity baselines, lower bounds             | none                       | DRIVE, WALK, BIKE, TRANSIT, DRIVE_TRANSIT   |
| OSRM, Valhalla     | *Planned*                                  | tba                        | DRIVE, WALK, BIKE                           |

All backends return a `TravelMatrix`; all accept the same `Mode` enum.

---

## FalcomChain interop

The output of any backend is dropped straight into FalcomChain:

```python
Assignment.travel_times = MappingProxyType(matrix.as_dict())
```

`matrix.as_dict()` returns `{(facility_node, demand_node): seconds}`, the
exact shape consumed by FalcomChain's energy and minimax-radius routines.

---

## License

MIT — see [LICENSE](LICENSE).
