# Load the model: packages and all functions in model/R/.
#   source("model/load.R")   (from the toolkit's top folder)
suppressPackageStartupMessages({
  library(dplyr)
  library(tidyr)
  library(purrr)
  library(stringr)
  library(readr)
  library(tibble)
})
local({
  here <- if (exists("TOOLKIT_ROOT")) TOOLKIT_ROOT else getwd()
  for (f in list.files(file.path(here, "model", "R"), pattern = "\\.R$", full.names = TRUE)) {
    source(f, local = globalenv())
  }
})
