import os
import re
import subprocess

from tqdm.auto import tqdm


def run_ttm(
    r_script_path,
    data_path,
    origins_path,
    dest_path,
    departure_time="2025-09-08 09:00:00",
    max_trip_duration=600,
    max_walk_time=120,
    memory_limit_gb=8,
):
    """
    Python wrapper to call an external R script that runs r5r::travel_time_matrix.
    """

    # --- sanity checks ---
    if not os.path.exists(r_script_path):
        raise FileNotFoundError(f"R script not found: {r_script_path}")

    for path in [data_path, origins_path, dest_path]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing input path: {path}")

    # --- build command ---
    cmd = [
        "Rscript",
        r_script_path,
        data_path,
        origins_path,
        dest_path,
        departure_time,
        str(max_trip_duration),
        str(max_walk_time),
        str(memory_limit_gb),
    ]

    print("Running:", " ".join(cmd))

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # ensures real-time line-by-line streaming
    )

    print("R script running, streaming output...\n")

    progress_re = re.compile(r"(\d+)\s+of\s+(\d+)\s+origins", re.IGNORECASE)
    pbar = None

    for line in process.stdout:
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


if __name__ == "__main__":
    run_ttm(
        r_script_path="/Users/kirtisoglu/Documents/Documents/GitHub/Allocation-of-Primary-Care-Centers-in-Chicago/falcomchain/travel_time/ttm.R",
        data_path="/Users/kirtisoglu/Documents/Documents/GitHub/Allocation-of-Primary-Care-Centers-in-Chicago/data/network-data",
        origins_path="/Users/kirtisoglu/Documents/Documents/GitHub/Allocation-of-Primary-Care-Centers-in-Chicago/data/network-data/origins.csv",
        dest_path="/Users/kirtisoglu/Documents/Documents/GitHub/Allocation-of-Primary-Care-Centers-in-Chicago/data/network-data/destinations.csv",
    )
