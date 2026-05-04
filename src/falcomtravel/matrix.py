"""TravelMatrix — container around a ``(origin, dest) -> seconds`` dict.

This is the canonical output format. The underlying dict is what FalcomChain's
``Assignment.travel_times`` consumes directly:

>>> matrix = TravelMatrix(...)
>>> from types import MappingProxyType
>>> Assignment.travel_times = MappingProxyType(matrix.as_dict())
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Hashable

from .modes import Mode

NodeId = Hashable
Pair = tuple[NodeId, NodeId]


@dataclass
class TravelMatrix:
    """A sparse OD matrix keyed by ``(origin, destination)``.

    :param data: Dict ``{(origin, dest): seconds}``. Tuple key, numeric value.
    :param mode: The travel mode that produced this matrix.
    :param meta: Free-form metadata (engine version, params, departure_time, ...).
    :param unreachable: Pairs that were attempted but had no route. Distinct
        from "not in the matrix at all" — these were tried and failed.
    """

    data: dict[Pair, float] = field(default_factory=dict)
    mode: Mode | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    unreachable: set[Pair] = field(default_factory=set)

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, pair: Pair) -> float:
        return self.data[pair]

    def __contains__(self, pair: object) -> bool:
        return pair in self.data

    def __iter__(self):
        return iter(self.data)

    def get(self, pair: Pair, default: float | None = None) -> float | None:
        return self.data.get(pair, default)

    def origins(self) -> set[NodeId]:
        return {o for o, _ in self.data}

    def destinations(self) -> set[NodeId]:
        return {d for _, d in self.data}

    def as_dict(self) -> dict[Pair, float]:
        """Return the underlying dict (for ``Assignment.travel_times``)."""
        return self.data

    def filter_by_origins(self, origins: Iterable[NodeId]) -> "TravelMatrix":
        keep = set(origins)
        return TravelMatrix(
            data={(o, d): t for (o, d), t in self.data.items() if o in keep},
            mode=self.mode,
            meta=dict(self.meta),
            unreachable={(o, d) for (o, d) in self.unreachable if o in keep},
        )

    def fill_missing(
        self,
        nodes: Iterable[NodeId],
        candidates: Iterable[NodeId],
        value: float = 0.0,
    ) -> int:
        """Fill missing ``(candidate, node)`` pairs with ``value``.

        Useful for nodes that the routing engine couldn't reach (typically
        topologically disconnected). Returns the number of pairs added.

        :param nodes: All nodes in the underlying graph.
        :param candidates: Origin candidates that need full coverage.
        :param value: Fill value (default 0.0).
        """
        nodes_set = set(nodes)
        added = 0
        for c in candidates:
            for n in nodes_set:
                pair = (c, n)
                if pair not in self.data:
                    self.data[pair] = float(value)
                    added += 1
        return added

    def to_parquet(self, path: str | Path) -> None:
        """Persist as long-format parquet (columns: origin, dest, seconds)."""
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError("to_parquet requires pandas") from e

        df = pd.DataFrame(
            (
                (o, d, t)
                for (o, d), t in self.data.items()
            ),
            columns=["origin", "dest", "seconds"],
        )
        df.to_parquet(path, index=False)

    @classmethod
    def from_parquet(
        cls,
        path: str | Path,
        *,
        origin_col: str = "from_id",
        dest_col: str = "to_id",
        time_col: str = "travel_time_p50",
        partitioned: bool = True,
        cast: type = int,
        mode: Mode | None = None,
    ) -> "TravelMatrix":
        """Load from r5r-style parquet output.

        Handles both a single parquet file and the partitioned dataset
        layout that ``r5r::write_dataset(partitioning="from_id")`` produces
        (directories named ``from_id=<id>/part-*.parquet``).

        :param origin_col: Column name in the parquet file.
        :param dest_col: Column name.
        :param time_col: Column name (default r5r's median).
        :param partitioned: If True (default), traverse subdirectories and
            recover the origin from the ``from_id=<id>`` partition path.
        :param cast: Cast both origin and dest IDs through this callable
            (default ``int`` — set to ``str`` to keep them as strings).
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError("from_parquet requires pandas + pyarrow") from e
        import re

        base = Path(path)
        data: dict[Pair, float] = {}

        if base.is_file() or not partitioned:
            df = pd.read_parquet(base)
            for o, d, t in zip(df[origin_col], df[dest_col], df[time_col]):
                data[(cast(o), cast(d))] = float(t)
        else:
            partition_re = re.compile(r"from_id=([^/]+)")
            for parquet in base.rglob("*.parquet"):
                m = partition_re.search(str(parquet))
                if m:
                    origin = cast(m.group(1))
                    df = pd.read_parquet(parquet, columns=[dest_col, time_col])
                    for d, t in zip(df[dest_col], df[time_col]):
                        data[(origin, cast(d))] = float(t)
                else:
                    df = pd.read_parquet(parquet)
                    for o, d, t in zip(df[origin_col], df[dest_col], df[time_col]):
                        data[(cast(o), cast(d))] = float(t)

        return cls(data=data, mode=mode, meta={"source": str(base)})

    @classmethod
    def from_dict(
        cls,
        data: Mapping[Pair, float],
        *,
        mode: Mode | None = None,
    ) -> "TravelMatrix":
        return cls(data=dict(data), mode=mode)
