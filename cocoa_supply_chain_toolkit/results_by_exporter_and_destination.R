# =============================================================================
# results_by_exporter_and_destination.R: summary tables from a model run
# =============================================================================
# Run after run_model.R, from the toolkit's top folder:
#     Rscript results_by_exporter_and_destination.R              # Côte d'Ivoire example
#     Rscript results_by_exporter_and_destination.R cameroon
# (Set MODEL_OUTPUT_DIR if you set it for run_model.R.)
#
# Writes into output/<country>/summaries/:
#   by_exporter.csv     exports, share traced to a region, deforestation and
#                       emissions per exporter group, with a 95% range for the
#                       directly traced volume (from the Monte Carlo draws)
#   by_destination.csv  the same per importing country
#   by_region.csv       directly traced volume and deforestation per region
#
# A copy of this script is a good starting point for your own analysis.
# =============================================================================
suppressPackageStartupMessages(library(dplyr))

args <- commandArgs(trailingOnly = TRUE)
country <- if (length(args) >= 1) args[1] else "cote_divoire"
TOOLKIT_ROOT <- normalizePath(getwd())
source(file.path(TOOLKIT_ROOT, "model", "load.R"))
source(file.path(TOOLKIT_ROOT, "countries", country, "config.R"))
output_dir <- Sys.getenv("MODEL_OUTPUT_DIR", file.path(TOOLKIT_ROOT, "output", country))

with_deforestation <- file.path(output_dir, sub("\\.csv$", "_with_deforestation.csv", config$output_file))
has_deforestation <- file.exists(with_deforestation)
results <- readr::read_csv(if (has_deforestation) with_deforestation else file.path(output_dir, config$output_file),
                           show_col_types = FALSE)

# Sum the volume and, if available, the deforestation columns over a grouping
summarise_group <- function(df) {
  out <- df %>%
    summarise(EXPORTS_T = sum(BEAN_EQUIVALENT_KG) / 1000,
              DIRECT_T = sum(BEAN_EQUIVALENT_KG[SOURCING_TYPE == "DIRECT"]) / 1000,
              INDIRECT_T = sum(BEAN_EQUIVALENT_KG[SOURCING_TYPE == "INDIRECT"]) / 1000,
              UNKNOWN_T = sum(BEAN_EQUIVALENT_KG[SOURCING_TYPE == "UNKNOWN"]) / 1000,
              .groups = "drop") %>%
    mutate(DIRECT_SHARE = DIRECT_T / EXPORTS_T)
  if (has_deforestation) {
    defo <- df %>%
      summarise(DEFORESTATION_AND_DEGRADATION_HA_15Y = sum(DEFORESTATION_AND_DEGRADATION_HA_15Y),
                GROSS_EMISSIONS_TCO2_15Y = sum(GROSS_EMISSIONS_TCO2_15Y),
                NET_EMISSIONS_TCO2_15Y = sum(NET_EMISSIONS_TCO2_15Y),
                COCOA_LAND_HA = sum(COCOA_LAND_HA), .groups = "drop")
    out <- bind_cols(out, defo %>% select(-any_of(group_vars(df)))) %>%
      mutate(HA_PER_1000_T = DEFORESTATION_AND_DEGRADATION_HA_15Y / EXPORTS_T * 1000)
  }
  out
}

# 95% range of the directly traced volume per exporter group, from the draws
draws <- readRDS(file.path(output_dir, "intermediate", paste0("flows_with_draws_", config$year, ".rds")))
direct_range <- draws %>%
  filter(REGION_CODE != "UNKNOWN") %>%
  mutate(kg = lapply(BEAN_EQUIVALENT_KG_DRAWS, function(d) d[[1]]),
         draw = lapply(kg, seq_along)) %>%
  select(EXPORTER_GROUP, draw, kg) %>%
  tidyr::unnest(c(draw, kg)) %>%
  group_by(EXPORTER_GROUP, draw) %>%
  summarise(kg = sum(kg), .groups = "drop") %>%
  group_by(EXPORTER_GROUP) %>%
  summarise(DIRECT_T_LOW_95 = quantile(kg, 0.025) / 1000,
            DIRECT_T_HIGH_95 = quantile(kg, 0.975) / 1000)

by_exporter <- results %>% group_by(EXPORTER_GROUP) %>% summarise_group() %>%
  left_join(direct_range, by = "EXPORTER_GROUP") %>%
  mutate(across(c(DIRECT_T_LOW_95, DIRECT_T_HIGH_95), ~ coalesce(.x, 0))) %>%   # nothing traced
  arrange(desc(EXPORTS_T))
by_destination <- results %>% group_by(COUNTRY_OF_DESTINATION) %>% summarise_group() %>%
  arrange(desc(EXPORTS_T))
by_region <- results %>% filter(SOURCING_TYPE == "DIRECT") %>%
  group_by(REGION_ID, REGION_NAME) %>% summarise_group() %>%
  select(-INDIRECT_T, -UNKNOWN_T, -DIRECT_SHARE) %>%
  arrange(desc(EXPORTS_T))

summary_dir <- file.path(output_dir, "summaries")
dir.create(summary_dir, showWarnings = FALSE)
readr::write_csv(by_exporter, file.path(summary_dir, "by_exporter.csv"))
readr::write_csv(by_destination, file.path(summary_dir, "by_destination.csv"))
readr::write_csv(by_region, file.path(summary_dir, "by_region.csv"))
message("Summaries written to ", summary_dir)
print(by_exporter, width = Inf)
