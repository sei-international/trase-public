# =============================================================================
# run_model.R: run the supply-chain model (and deforestation exposure) for one country
# =============================================================================
# From the toolkit's top folder:
#     Rscript run_model.R                     # Côte d'Ivoire example (synthetic data)
#     Rscript run_model.R cameroon            # once countries/cameroon/ exists
#
# Settings via environment variables:
#     MODEL_DATA_DIR   folder with the input files (default: synthetic example)
#     MODEL_N_DRAWS    Monte Carlo draws (default 1000; use e.g. 50 to test)
#     MODEL_OUTPUT_DIR where to write results (default: output/<country>)
# =============================================================================

args <- commandArgs(trailingOnly = TRUE)
country <- if (length(args) >= 1) args[1] else "cote_divoire"

TOOLKIT_ROOT <- normalizePath(getwd())
if (!dir.exists(file.path(TOOLKIT_ROOT, "model"))) stop("Run this from the toolkit's top folder.")
source(file.path(TOOLKIT_ROOT, "model", "load.R"))

country_dir <- file.path(TOOLKIT_ROOT, "countries", country)
if (!dir.exists(country_dir)) stop("No country folder: ", country_dir)
source(file.path(country_dir, "config.R"))       # defines `config`
source(file.path(country_dir, "read_inputs.R"))  # defines read_inputs()

output_dir <- Sys.getenv("MODEL_OUTPUT_DIR", file.path(TOOLKIT_ROOT, "output", country))
message("Country: ", country, " | data: ", config$data_dir, " | draws: ", config$n_draws)

raw    <- read_inputs(config)
inputs <- prepare_inputs(raw, config)
result <- run_supply_chain_model(inputs, config)
out    <- write_model_outputs(result, inputs, config, output_dir)

message("\nShare of exported volume by type of sourcing:")
print(result$diagnostics$sourcing_summary)
if (length(result$diagnostics$exporters_that_may_be_cooperatives) > 0) {
  message("\nExporters that are neither known cooperatives nor disclosing companies ",
          "(check whether any is a cooperative missing from exporting_cooperative_rules.csv):")
  print(result$diagnostics$exporters_that_may_be_cooperatives)
}
if (length(result$diagnostics$disclosing_buyers_not_in_customs) > 0) {
  message("\nCompanies that disclose suppliers but match no exporter or importer in ",
          "customs data (their links are not used; check the name spelling):")
  print(result$diagnostics$disclosing_buyers_not_in_customs)
}
message("\nResult written to ", out)

# --- Deforestation exposure ----------------------------------------------------
# Runs when the country's read_inputs.R defines read_spatial_inputs() (see
# docs/HOW_THE_MODEL_WORKS.md, "From the model to deforestation exposure"). Writes
# one row per flow with its cocoa deforestation and degradation (ha), emissions
# (t CO2) and cocoa land (ha).
if (exists("read_spatial_inputs")) {
  spatial  <- read_spatial_inputs(config)
  exposure <- run_exposure(result, spatial, config)
  exposure_file <- file.path(output_dir, sub("\\.csv$", "_with_deforestation.csv", config$output_file))
  readr::write_csv(exposure$flows, exposure_file)
  saveRDS(exposure, file.path(output_dir, "intermediate", paste0("deforestation_per_tonne_", config$year, ".rds")))
  message("\nCocoa deforestation and degradation linked to exports (ha, 15-year total): ",
          format(round(sum(exposure$flows$DEFORESTATION_AND_DEGRADATION_HA_15Y, na.rm = TRUE)), big.mark = ","))
  message("Supply chains with deforestation written to ", exposure_file)
} else {
  message("\nNo read_spatial_inputs() for this country: deforestation exposure skipped.")
}
