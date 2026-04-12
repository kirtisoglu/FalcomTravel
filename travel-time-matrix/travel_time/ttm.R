# ttm.R

# =========================================================
# Chicago Travel Time Matrix Script (CLI-ready version)
# =========================================================
# Usage:
#   Rscript ttm.R <data_path> <origins_path> <dest_path> <departure_time> <max_trip_duration> <max_walk_time> <memory_limit_gb>
#
# Example:
#   Rscript ttm.R \
#       "/Users/kirtisoglu/Documents/GitHub/Chicago-Travel-Time-Matrix/network-data" \
#       "/Users/kirtisoglu/Documents/GitHub/Chicago-Travel-Time-Matrix/network-data/origins.csv" \
#       "/Users/kirtisoglu/Documents/GitHub/Chicago-Travel-Time-Matrix/network-data/destinations.csv" \
#       "2025-09-08 09:00:00" 600 120 8
# =========================================================


# --- get command-line args ---
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 7) {
  stop("Usage: Rscript ttm.R <data_path> <origins_path> <dest_path> <departure_time> <max_trip_duration> <max_walk_time> <memory_limit_gb>")
}

data_path <- args[1]
origins_path <- args[2]
dest_path <- args[3]
departure_time <- args[4]
max_trip_duration <- as.numeric(args[5])
max_walk_time <- as.numeric(args[6])
memory_limit_gb <- as.numeric(args[7])

# --- set how much memory R can allocate to Java, which is what the r5r package runs on internally ---
options(java.parameters = paste0("-Xmx", memory_limit_gb, "G"))

# --- libs ---
suppressPackageStartupMessages({
  library(r5r)
  library(dplyr)
  library(readr)
  library(arrow)
  library(parallel)
})

# --- path checks ---
if (!dir.exists(data_path)) stop(paste("Network data directory not found:", data_path))
if (!file.exists(origins_path)) stop(paste("Origins file not found:", origins_path))
if (!file.exists(dest_path)) stop(paste("Destinations file not found:", dest_path))

# --- load OD points ---
message("Loading origins and destinations...")
origins <- read_csv(origins_path, show_col_types = FALSE) |> mutate(id = as.character(id))
destinations <- read_csv(dest_path, show_col_types = FALSE) |> mutate(id = as.character(id))

# --- build/load core ---
message("Setting up R5R core...")
r5r_core <- setup_r5(data_path = data_path, verbose = TRUE)

# --- run TTM ---
message("Running travel_time_matrix...")
ttm <- travel_time_matrix(
  r5r_core           = r5r_core,
  origins            = origins,
  destinations       = destinations,
  mode               = c("WALK", "TRANSIT"),
  departure_datetime = as.POSIXct(departure_time, tz = "America/Chicago"),
  max_trip_duration  = max_trip_duration,
  max_walk_time      = max_walk_time,
  n_threads          = max(1, detectCores() - 1),
  progress           = TRUE
)

message("Travel time matrix computed.")
message("Dimensions: ", paste(dim(ttm), collapse = " x "))
message("Columns: ", paste(names(ttm), collapse = ", "))

# --- ensure IDs are character ---
ttm$from_id <- as.character(ttm$from_id)
ttm$to_id <- as.character(ttm$to_id)

# --- save results partitioned by origin ---
output_dir <- file.path(dirname(dest_path), "ttm_parquet")
message("Saving results to: ", output_dir)
write_dataset(
  ttm,
  path = output_dir,
  format = "parquet",
  partitioning = "from_id"
)

message("Travel time matrix successfully saved to parquet dataset.")

# --- stop core ---
stop_r5(r5r_core)
message("R5R core stopped successfully.")
