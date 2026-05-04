# falcomtravel/backends/_r/ttm.R
#
# r5r::travel_time_matrix wrapper.
#
# Usage (called from Python via R5RBackend; not intended for hand use):
#   Rscript ttm.R <data_path> <origins_csv> <dest_csv> <output_dir> \
#                 <mode> <departure_time> <max_trip_duration> \
#                 <max_walk_time> <memory_limit_gb> <timezone>
#
# All paths are absolute. ``mode`` is a comma-separated list of r5r mode
# names (e.g. "CAR" or "WALK,TRANSIT"). ``departure_time`` is parsed in
# ``timezone`` as ISO-ish ("YYYY-MM-DD HH:MM:SS").

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 10) {
  stop(paste(
    "Usage: Rscript ttm.R <data_path> <origins_csv> <dest_csv> <output_dir>",
    "<mode> <departure_time> <max_trip_duration> <max_walk_time>",
    "<memory_limit_gb> <timezone>"
  ))
}

data_path         <- args[1]
origins_path      <- args[2]
dest_path         <- args[3]
output_dir        <- args[4]
mode_arg          <- args[5]
departure_time    <- args[6]
max_trip_duration <- as.numeric(args[7])
max_walk_time     <- as.numeric(args[8])
memory_limit_gb   <- as.numeric(args[9])
timezone          <- args[10]

modes <- strsplit(mode_arg, ",", fixed = TRUE)[[1]]

options(java.parameters = paste0("-Xmx", memory_limit_gb, "G"))

suppressPackageStartupMessages({
  library(r5r)
  library(dplyr)
  library(readr)
  library(arrow)
  library(parallel)
})

if (!dir.exists(data_path))      stop(paste("Network data directory not found:", data_path))
if (!file.exists(origins_path))  stop(paste("Origins file not found:", origins_path))
if (!file.exists(dest_path))     stop(paste("Destinations file not found:", dest_path))

message("Loading origins and destinations...")
origins      <- read_csv(origins_path, show_col_types = FALSE) |> mutate(id = as.character(id))
destinations <- read_csv(dest_path,    show_col_types = FALSE) |> mutate(id = as.character(id))

message("Setting up R5R core...")
r5r_core <- setup_r5(data_path = data_path, verbose = TRUE)

message("Running travel_time_matrix with mode=", paste(modes, collapse = "+"), " ...")
ttm <- travel_time_matrix(
  r5r_core           = r5r_core,
  origins            = origins,
  destinations       = destinations,
  mode               = modes,
  departure_datetime = as.POSIXct(departure_time, tz = timezone),
  max_trip_duration  = max_trip_duration,
  max_walk_time      = max_walk_time,
  n_threads          = max(1, detectCores() - 1),
  progress           = TRUE
)

message("Travel time matrix computed.")
message("Dimensions: ", paste(dim(ttm), collapse = " x "))
message("Columns: ", paste(names(ttm), collapse = ", "))

ttm$from_id <- as.character(ttm$from_id)
ttm$to_id   <- as.character(ttm$to_id)

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
message("Saving results to: ", output_dir)
write_dataset(
  ttm,
  path         = output_dir,
  format       = "parquet",
  partitioning = "from_id"
)

message("Travel time matrix successfully saved to parquet dataset.")

stop_r5(r5r_core)
message("R5R core stopped successfully.")
