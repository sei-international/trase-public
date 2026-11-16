# =============================================================================
# test_model_results.R: does the model still give the expected results?
# =============================================================================
# Runs the model (50 draws, fixed seed) on
#   - the synthetic Côte d'Ivoire example (data/synthetic_cote_divoire), and
#   - test data that triggers every special case (tests/data_branch_coverage,
#     made by tests/make_branch_test_data.py)
# and compares the output table and the supplier links with the saved results
# in tests/expected/. Use it after any change to the code in model/: a
# change that is not meant to alter results must leave them identical.
#
# Run from the toolkit's top folder:
#     Rscript tests/test_model_results.R
# After a change that is MEANT to alter results, check the new results, then
# save them as the new expected results with:
#     Rscript tests/test_model_results.R --update
# =============================================================================
suppressMessages(library(dplyr))
TOOLKIT_ROOT <- normalizePath(getwd())
update <- "--update" %in% commandArgs(trailingOnly = TRUE)
Sys.setenv(MODEL_N_DRAWS = "50")
source(file.path(TOOLKIT_ROOT, "model", "load.R"))
source(file.path(TOOLKIT_ROOT, "countries", "cote_divoire", "read_inputs.R"))

if (!dir.exists(file.path(TOOLKIT_ROOT, "tests", "data_branch_coverage"))) {
  system2("python3", file.path(TOOLKIT_ROOT, "tests", "make_branch_test_data.py"), stdout = FALSE)
}
datasets <- c(example = file.path(TOOLKIT_ROOT, "data", "synthetic_cote_divoire"),
              special_cases = file.path(TOOLKIT_ROOT, "tests", "data_branch_coverage"))

expected_file <- function(name, what) file.path(TOOLKIT_ROOT, "tests", "expected", paste0(name, "_", what, ".csv"))
# round to 6 significant digits so the test does not depend on the platform's
# last floating-point digit
tidy <- function(d) d %>% mutate(across(where(is.numeric), ~ signif(.x, 6))) %>% as.data.frame()

ok <- TRUE
for (name in names(datasets)) {
  Sys.setenv(MODEL_DATA_DIR = datasets[[name]])
  source(file.path(TOOLKIT_ROOT, "countries", "cote_divoire", "config.R"))
  result <- run_supply_chain_model(prepare_inputs(read_inputs(config), config), config, verbose = FALSE)
  got <- list(
    output = tidy(result$output),
    supplier_links = tidy(result$supplier_links %>%
                            select(where(~ !is.list(.x))) %>%
                            arrange(across(everything())))
  )
  for (what in names(got)) {
    f <- expected_file(name, what)
    if (update) {
      readr::write_csv(got[[what]], f)
      message("saved ", basename(f))
      next
    }
    read <- function(path) as.data.frame(readr::read_csv(path, show_col_types = FALSE, guess_max = 1e6,
                                                         col_types = readr::cols(.default = "c")))
    tmp <- tempfile(fileext = ".csv"); readr::write_csv(got[[what]], tmp)
    want <- read(f); got[[what]] <- read(tmp)   # compare the files as text
    same <- isTRUE(all.equal(want, got[[what]], check.attributes = FALSE))
    ok <- ok && same
    message(if (same) "PASS  " else "FAIL  ", name, ": ", what, " as expected (", nrow(got[[what]]), " rows)")
  }
}
Sys.unsetenv("MODEL_DATA_DIR")
if (!ok) quit(status = 1)
