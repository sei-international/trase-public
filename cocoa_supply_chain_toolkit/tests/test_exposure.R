# =============================================================================
# test_exposure.R: checks of the deforestation-exposure steps
# (model/R/deforestation_exposure.R), on the synthetic example
# =============================================================================
# Each check recomputes a step by hand, the way docs/HOW_THE_MODEL_WORKS.md describes it,
# and compares it with the function.
# Run from the toolkit's top folder:  Rscript tests/test_exposure.R
# =============================================================================
suppressMessages(library(dplyr))
TOOLKIT_ROOT <- normalizePath(getwd())
Sys.setenv(MODEL_N_DRAWS = "30")
source(file.path(TOOLKIT_ROOT, "model", "load.R"))
source(file.path(TOOLKIT_ROOT, "countries", "cote_divoire", "config.R"))
source(file.path(TOOLKIT_ROOT, "countries", "cote_divoire", "read_inputs.R"))
inputs <- prepare_inputs(read_inputs(config), config)
result <- run_supply_chain_model(inputs, config, verbose = FALSE)
spatial <- read_spatial_inputs(config)
exposure <- suppressWarnings(run_exposure(result, spatial, config))

ok <- TRUE
check <- function(pass, what) {
  message(if (isTRUE(pass)) "PASS  " else "FAIL  ", what)
  ok <<- ok && isTRUE(pass)
}
near <- function(a, b) isTRUE(all.equal(as.vector(a), as.vector(b), tolerance = 1e-9, check.attributes = FALSE))

# --- Step 1: untraced weights ----------------------------------------------------
# untraced production of a region = production - volume sourced from it
# (floored at 0); weight = its share of the national untraced total
direct <- tapply(result$output$BEAN_EQUIVALENT_KG, result$output$REGION_ID, sum)
p <- spatial$production
d <- direct[p$REGION_ID]; d[is.na(d)] <- 0
surplus <- pmax(p$COCOA_PRODUCTION_KG - d, 0)
w <- exposure$weights[match(p$REGION_ID, exposure$weights$REGION_ID), ]
check(near(w$SHARE_OF_UNTRACED_PRODUCTION, surplus / sum(surplus)), "untraced weights = share of production not sourced directly")
check(near(sum(w$SHARE_OF_UNTRACED_PRODUCTION), 1), "untraced weights add up to 1")

# --- Step 2: per-tonne metrics ---------------------------------------------------
pt <- exposure$per_tonne %>% filter(YEAR == config$year)
m <- spatial$region_metrics %>% filter(YEAR == config$year)
reg <- pt[match(m$REGION_ID, pt$REGION_ID), ]
check(near(reg$DEFORESTATION_AND_DEGRADATION_HA_PER_T_15Y, m$COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL / m$COCOA_TONNES),
      "region: deforestation and degradation per tonne = metric / production")
check(near(reg$GROSS_EMISSIONS_TCO2_PER_T_ANNUAL, m$COCOA_GROSS_EMISSIONS_ANNUAL / m$COCOA_TONNES),
      "region: emissions per tonne = metric / production")
check(near(reg$COCOA_LAND_HA_PER_T, m$COCOA_HA / m$COCOA_TONNES), "region: cocoa land per tonne = cocoa area / production")
wt <- exposure$weights$SHARE_OF_UNTRACED_PRODUCTION[match(m$REGION_ID, exposure$weights$REGION_ID)]
expected_untraced <- weighted.mean(m$COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL / m$COCOA_TONNES, wt)
for (id in c(config$ids$unknown_region_id, config$ids$indirect_region_id)) {
  check(near(pt$DEFORESTATION_AND_DEGRADATION_HA_PER_T_15Y[pt$REGION_ID == id], expected_untraced),
        paste0(id, ": per tonne = regional values weighted by untraced weights"))
}

# --- Step 3: exposure per flow ---------------------------------------------------
f <- exposure$flows
per_t <- pt$DEFORESTATION_AND_DEGRADATION_HA_PER_T_15Y[match(f$REGION_ID, pt$REGION_ID)]
check(nrow(f) == nrow(result$output), "one row per flow")
check(!anyNA(f$DEFORESTATION_AND_DEGRADATION_HA_15Y), "every flow gets an exposure value")
check(near(f$DEFORESTATION_AND_DEGRADATION_HA_15Y, f$BEAN_EQUIVALENT_KG / 1000 * per_t),
      "exposure = volume (t) x per-tonne figure of the flow's region")
check(near(sum(f$BEAN_EQUIVALENT_KG), sum(result$output$BEAN_EQUIVALENT_KG)), "volumes unchanged")

# --- Step 4: optional extras -----------------------------------------------------
check(all(f$ECOREGION[f$SOURCING_TYPE != "DIRECT"] == "UNKNOWN") && !anyNA(f$ECOREGION),
      "region attribute added; UNKNOWN for indirect and unknown flows")
cm <- f %>% distinct(EXPORTER_GROUP, ZERO_DEFORESTATION_COMMITMENT)
check(cm$ZERO_DEFORESTATION_COMMITMENT[cm$EXPORTER_GROUP == "ARBORIA CACAO NEGOCE"] == "ZERO DEFORESTATION",
      "commitment in force in the model year is reported")
check(cm$ZERO_DEFORESTATION_COMMITMENT[cm$EXPORTER_GROUP == "BRISEFEVE EXPORT"] == "NONE",
      "commitment starting after the model year counts as none")
check(cm$ZERO_DEFORESTATION_COMMITMENT[cm$EXPORTER_GROUP == "ELYSEE TRADING"] == "UNKNOWN",
      "exporter not in the commitments table is unknown")

if (!ok) quit(status = 1)
