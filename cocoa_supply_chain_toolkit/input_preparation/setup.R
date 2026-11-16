# Shared setup for the input-preparation scripts.
#   - finds the toolkit folder (run scripts from the toolkit's top folder)
#   - loads the toolkit functions (str_trans() etc.) and the helpers here
#   - input_path(): files under MODEL_DATA_DIR (default: the synthetic raw inputs in
#     data/synthetic_raw_inputs/, made by data/make_synthetic_raw_inputs.py)
#   - require_input(): stops with a clear message if a file is missing
if (!exists("TOOLKIT_ROOT")) TOOLKIT_ROOT <- normalizePath(getwd())
if (!dir.exists(file.path(TOOLKIT_ROOT, "model"))) stop("Run from the toolkit's top folder.")
source(file.path(TOOLKIT_ROOT, "model", "load.R"))
suppressPackageStartupMessages(library(tidyverse))
for (f in list.files(file.path(TOOLKIT_ROOT, "input_preparation", "helpers"), "\\.R$", full.names = TRUE)) source(f)
DATA_DIR <- Sys.getenv("MODEL_DATA_DIR", file.path(TOOLKIT_ROOT, "data", "synthetic_raw_inputs"))
input_path <- function(...) file.path(DATA_DIR, ...)
require_input <- function(path) {
  if (!file.exists(path)) stop("Input file not found: ", path, call. = FALSE)
  path
}

# These scripts were written to be run line by line in RStudio, and call
# View() to show tables. When run with Rscript, View() does nothing.
if (!interactive()) View <- function(x, ...) invisible(x)
