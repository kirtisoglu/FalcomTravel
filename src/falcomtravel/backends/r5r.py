"""r5r backend — multimodal routing via Rscript shellout.

Wraps the bundled ``ttm.R`` script, which calls ``r5r::travel_time_matrix``
under the hood. Requires R, Java, and the ``r5r`` R package to be installed.

The script writes a partitioned parquet dataset (one directory per origin)
and this backend reads it back into a :class:`TravelMatrix`. For datasets
in the millions of OD pairs, prefer keeping the parquet on disk and
loading it once with :meth:`TravelMatrix.from_parquet`.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from collections.abc import Iterable
from importlib.resources import files
from pathlib import Path
from typing import Hashable

from tqdm.auto import tqdm

from ..matrix import TravelMatrix
from ..modes import Mode

_MODE_MAP: dict[Mode, list[str]] = {
    Mode.DRIVE:         ["CAR"],
    Mode.WALK:          ["WALK"],
    Mode.BIKE:          ["BICYCLE"],
    Mode.TRANSIT:       ["WALK", "TRANSIT"],
    Mode.DRIVE_TRANSIT: ["CAR_PARK", "TRANSIT"],
}


class R5RBackend:
    """Run r5r's ``travel_time_matrix`` against an OSM/GTFS network.

    :param data_path: Directory containing the OSM ``.pbf`` and (optionally)
        GTFS ``.zip`` files that r5r will index. r5r writes its network cache
        into this directory the first time the script runs.
    :param coords: ``{node_id: (lon, lat)}`` for every node that may appear
        as an origin or destination. Required because r5r needs lat/lon CSVs.
    :param timezone: IANA timezone for ``departure_time`` (e.g.
        ``"America/Chicago"``, ``"Europe/London"``).
    :param r_script: Override the bundled ``ttm.R``. Defaults to the
        version shipped inside the package.
    :param rscript_bin: ``Rscript`` executable name on PATH. Override if
        you have a non-standard R install.
    """

    name = "r5r"

    def __init__(
        self,
        data_path: str | Path,
        coords: dict[Hashable, tuple[float, float]],
        *,
        timezone: str = "UTC",
        r_script: str | Path | None = None,
        rscript_bin: str = "Rscript",
    ):
        self.data_path = Path(data_path)
        self.coords = coords
        self.timezone = timezone
        self.rscript_bin = rscript_bin
        self.r_script = (
            Path(r_script)
            if r_script is not None
            else Path(files("falcomtravel.backends._r").joinpath("ttm.R"))
        )

        if not self.r_script.exists():
            raise FileNotFoundError(f"R script not found: {self.r_script}")
        if not self.data_path.exists():
            raise FileNotFoundError(f"Network data dir not found: {self.data_path}")

    def supports(self, mode: Mode) -> bool:
        return Mode.parse(mode) in _MODE_MAP

    def compute(
        self,
        origins: Iterable[Hashable],
        destinations: Iterable[Hashable],
        mode: Mode,
        *,
        departure_time: str = "2025-09-08 09:00:00",
        max_trip_duration: int = 600,
        max_walk_time: int = 120,
        memory_limit_gb: int = 8,
        output_dir: str | Path | None = None,
        cast: type = int,
        keep_parquet: bool = False,
    ) -> TravelMatrix:
        """Run r5r and read the result back as a :class:`TravelMatrix`.

        :param departure_time: ``"YYYY-MM-DD HH:MM:SS"`` in ``self.timezone``.
        :param max_trip_duration: Cap on per-OD travel time in **minutes**
            (r5r's unit). Pairs exceeding this are silently dropped by r5r.
        :param max_walk_time: Cap on access/egress walking time in **minutes**.
        :param memory_limit_gb: Java heap (``-Xmx``) for the r5 engine.
        :param output_dir: Where to write the parquet dataset. If None, a
            temp dir is used and deleted unless ``keep_parquet=True``.
        :param cast: Cast IDs read back from parquet through this callable.
            Default ``int`` matches the rest of falcomtravel; use ``str`` if
            your graph nodes are strings.
        :param keep_parquet: If True, leave the parquet dataset on disk
            even when ``output_dir`` was a tempdir.
        """
        mode = Mode.parse(mode)
        if not self.supports(mode):
            raise ValueError(f"r5r backend does not support {mode}")
        r5r_modes = ",".join(_MODE_MAP[mode])

        origins = list(origins)
        destinations = list(destinations)
        self._check_coords(origins, "origin")
        self._check_coords(destinations, "destination")

        ctx = tempfile.TemporaryDirectory() if output_dir is None else _NullCtx()
        with ctx as tmp:
            workdir = Path(tmp) if output_dir is None else Path(output_dir)
            workdir.mkdir(parents=True, exist_ok=True)
            origins_csv = workdir / "origins.csv"
            dest_csv = workdir / "destinations.csv"
            ttm_dir = workdir / "ttm_parquet"

            self._write_points(origins, origins_csv)
            self._write_points(destinations, dest_csv)

            cmd = [
                self.rscript_bin,
                str(self.r_script),
                str(self.data_path),
                str(origins_csv),
                str(dest_csv),
                str(ttm_dir),
                r5r_modes,
                departure_time,
                str(max_trip_duration),
                str(max_walk_time),
                str(memory_limit_gb),
                self.timezone,
            ]
            self._run(cmd)

            matrix = TravelMatrix.from_parquet(
                ttm_dir,
                partitioned=True,
                cast=cast,
                mode=mode,
            )
            matrix.meta.update({
                "backend": self.name,
                "r5r_modes": r5r_modes,
                "departure_time": departure_time,
                "timezone": self.timezone,
                "max_trip_duration": max_trip_duration,
                "max_walk_time": max_walk_time,
            })

            origin_set = {cast(o) for o in origins}
            dest_set = {cast(d) for d in destinations}
            for o in origin_set:
                for d in dest_set:
                    if (o, d) not in matrix.data:
                        matrix.unreachable.add((o, d))

            if keep_parquet and output_dir is None:
                final = self.data_path / "ttm_parquet_kept"
                final.mkdir(exist_ok=True)
                matrix.meta["parquet_path"] = str(ttm_dir)

        return matrix

    def _check_coords(self, ids: list[Hashable], label: str) -> None:
        missing = [i for i in ids if i not in self.coords]
        if missing:
            sample = missing[:5]
            raise KeyError(
                f"{len(missing)} {label} IDs are missing from coords (e.g. {sample}). "
                f"Every origin and destination must have a (lon, lat) entry."
            )

    def _write_points(self, ids: list[Hashable], path: Path) -> None:
        with path.open("w") as f:
            f.write("id,lon,lat\n")
            for i in ids:
                lon, lat = self.coords[i]
                f.write(f"{i},{lon},{lat}\n")

    def _run(self, cmd: list[str]) -> None:
        print("Running:", " ".join(cmd))
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        progress_re = re.compile(r"(\d+)\s+of\s+(\d+)\s+origins", re.IGNORECASE)
        pbar = None
        for line in process.stdout:  # type: ignore[union-attr]
            print(line, end="")
            match = progress_re.search(line)
            if match:
                current = int(match.group(1))
                total = int(match.group(2))
                if pbar is None:
                    pbar = tqdm(total=total)
                pbar.n = current
                pbar.refresh()
        process.wait()
        if pbar is not None:
            pbar.close()
        if process.returncode != 0:
            raise RuntimeError(f"Rscript exited with code {process.returncode}")


class _NullCtx:
    """Context manager that yields ``None``, for the user-supplied output_dir path."""

    def __enter__(self):
        return None

    def __exit__(self, *_):
        return False
