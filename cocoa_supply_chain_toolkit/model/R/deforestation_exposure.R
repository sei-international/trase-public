# =============================================================================
# deforestation_exposure.R: link deforestation to supply-chain flows
# =============================================================================
# After the supply-chain model has run (run_supply_chain_model) and the
# deforestation metrics per region are computed (deforestation_metrics/), these
# steps give each flow its deforestation exposure:
#
#   1. untraced_region_weights()  how much each region contributes to the
#      country's UNTRACED cocoa (production not accounted for by direct
#      sourcing). Used to give indirect and unknown flows a weighted-average
#      figure per tonne (Renier et al. 2023, appendix, Eq. 6).
#   2. per_tonne_metrics()        cocoa deforestation and degradation,
#      emissions and cocoa land per tonne produced, per region, plus the
#      weighted averages for the INDIRECT and UNKNOWN pseudo-regions
#   3. deforestation_exposure()   flow volume (t) x per-tonne figure of its region
#   4. optional: add_region_attributes()   e.g. the ecoregion of each region
#                add_company_commitments() whether the exporter had a
#                                          zero-deforestation commitment
#
# "Cocoa deforestation and degradation" = undisturbed tropical moist forest
# lost (to deforestation OR degradation) where the cocoa map now shows cocoa;
# see docs/DEFORESTATION_METRICS.md. Emissions count deforestation only.
#
# run_exposure() runs everything. tests/test_exposure.R checks each step.
# =============================================================================

#' Step 1: share of the country's untraced production in each region.
#'
#' @param output     model output table (result$output)
#' @param production tibble with REGION_ID (as in the output) and
#'                   COCOA_PRODUCTION_KG (production in the model year)
#' @return one row per region: direct volume, production, untraced production
#'         and SHARE_OF_UNTRACED_PRODUCTION (sums to 1)
untraced_region_weights <- function(output, production) {
  w <- output %>%
    group_by(REGION_ID) %>%
    summarise(DIRECT_SOURCING_KG = sum(BEAN_EQUIVALENT_KG)) %>%
    ungroup() %>%
    # right join keeps regions not sourced from and drops INDIRECT/UNKNOWN
    right_join(production %>% select(REGION_ID, COCOA_PRODUCTION_KG), by = "REGION_ID") %>%
    mutate(
      DIRECT_SOURCING_KG = if_else(is.na(DIRECT_SOURCING_KG), 0, DIRECT_SOURCING_KG),
      # production not accounted for by direct sourcing (floored at 0)
      UNTRACED_PRODUCTION_KG = pmax(COCOA_PRODUCTION_KG - DIRECT_SOURCING_KG, 0),
      SHARE_OF_UNTRACED_PRODUCTION = UNTRACED_PRODUCTION_KG / sum(UNTRACED_PRODUCTION_KG)
    )
  if (round(sum(w$SHARE_OF_UNTRACED_PRODUCTION), 10) != 1) stop("untraced weights do not add up to 1")
  w
}

# Per-tonne figures computed in step 2: name in the output -> metric it divides
PER_TONNE <- c(
  DEFORESTATION_AND_DEGRADATION_HA_PER_T_15Y    = "COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL",
  DEFORESTATION_AND_DEGRADATION_HA_PER_T_ANNUAL = "COCOA_DEFORESTATION_AND_DEGRADATION_ANNUAL",
  GROSS_EMISSIONS_TCO2_PER_T_15Y                = "COCOA_GROSS_EMISSIONS_15_YEARS_TOTAL",
  GROSS_EMISSIONS_TCO2_PER_T_ANNUAL             = "COCOA_GROSS_EMISSIONS_ANNUAL",
  NET_EMISSIONS_TCO2_PER_T_15Y                  = "COCOA_NET_EMISSIONS_15_YEARS_TOTAL",
  NET_EMISSIONS_TCO2_PER_T_ANNUAL               = "COCOA_NET_EMISSIONS_ANNUAL",
  COCOA_LAND_HA_PER_T                           = "COCOA_HA"
)

#' Step 2: metrics per tonne produced, per region and year, plus weighted
#' averages for INDIRECT and UNKNOWN sourcing.
#'
#' @param region_metrics tibble with REGION_ID, YEAR, COCOA_TONNES (production),
#'   COCOA_HA (cocoa area) and the metrics in PER_TONNE above
#' @param weights tibble with REGION_ID, YEAR, SHARE_OF_UNTRACED_PRODUCTION
#' @param unknown_id,indirect_id the region IDs used for unknown and indirect sourcing
per_tonne_metrics <- function(region_metrics, weights, unknown_id, indirect_id) {
  per_region <- region_metrics %>%
    left_join(weights %>% select(REGION_ID, YEAR, SHARE_OF_UNTRACED_PRODUCTION),
              by = c("REGION_ID", "YEAR"))
  for (out in names(PER_TONNE)) {
    per_region[[out]] <- per_region[[PER_TONNE[[out]]]] / per_region$COCOA_TONNES
  }
  # regions with zero production
  per_region <- per_region %>%
    mutate(across(all_of(names(PER_TONNE)), ~ if_else(is.infinite(.x), NA_real_, .x)))

  untraced_average <- function(id) {
    per_region %>%
      group_by(YEAR) %>%
      summarise(across(all_of(names(PER_TONNE)),
                       ~ weighted.mean(.x, w = SHARE_OF_UNTRACED_PRODUCTION))) %>%
      mutate(REGION_ID = id)
  }

  bind_rows(per_region, untraced_average(unknown_id), untraced_average(indirect_id)) %>%
    # regions without a figure count as zero deforestation and land
    mutate(across(c(DEFORESTATION_AND_DEGRADATION_HA_PER_T_15Y, COCOA_LAND_HA_PER_T),
                  ~ replace(.x, is.na(.x), 0)))
}

# Exposure columns computed in step 3: name in the output -> per-tonne figure
EXPOSURE <- c(
  DEFORESTATION_AND_DEGRADATION_HA_15Y    = "DEFORESTATION_AND_DEGRADATION_HA_PER_T_15Y",
  DEFORESTATION_AND_DEGRADATION_HA_ANNUAL = "DEFORESTATION_AND_DEGRADATION_HA_PER_T_ANNUAL",
  GROSS_EMISSIONS_TCO2_15Y                = "GROSS_EMISSIONS_TCO2_PER_T_15Y",
  GROSS_EMISSIONS_TCO2_ANNUAL             = "GROSS_EMISSIONS_TCO2_PER_T_ANNUAL",
  NET_EMISSIONS_TCO2_15Y                  = "NET_EMISSIONS_TCO2_PER_T_15Y",
  NET_EMISSIONS_TCO2_ANNUAL               = "NET_EMISSIONS_TCO2_PER_T_ANNUAL",
  COCOA_LAND_HA                           = "COCOA_LAND_HA_PER_T"
)

#' Step 3: exposure of every flow = volume (bean equivalent, tonnes) x
#' per-tonne figure of the flow's region.
deforestation_exposure <- function(output, per_tonne) {
  flows <- output %>%
    left_join(per_tonne %>% select(REGION_ID, YEAR, all_of(names(PER_TONNE))),
              by = c("REGION_ID", "YEAR"))
  for (out in names(EXPOSURE)) {
    flows[[out]] <- flows$BEAN_EQUIVALENT_KG / 1000 * flows[[EXPOSURE[[out]]]]
  }
  flows %>% select(-all_of(names(PER_TONNE)))
}

#' Step 4a (optional): add attributes of each region, e.g. its ecoregion.
#' Indirect and unknown flows get "UNKNOWN".
#'
#' @param region_attributes tibble with REGION_ID and any other columns
add_region_attributes <- function(flows, region_attributes) {
  cols <- setdiff(names(region_attributes), "REGION_ID")
  flows %>%
    left_join(region_attributes, by = "REGION_ID") %>%
    mutate(across(all_of(cols), ~ if_else(SOURCING_TYPE == "DIRECT", as.character(.x), "UNKNOWN")))
}

#' Step 4b (optional): did the exporter have a zero-deforestation commitment
#' in force in the model year?
#'
#' @param commitments tibble with EXPORTER_GROUP, HAS_COMMITMENT (TRUE/FALSE),
#'   COMMITMENT_TYPE, START_YEAR, END_YEAR (empty if still in force)
#' @return flows with ZERO_DEFORESTATION_COMMITMENT: the commitment type if one
#'   was in force, "NONE" if the exporter is listed without one, "UNKNOWN" if
#'   the exporter is not listed
add_company_commitments <- function(flows, commitments, year) {
  in_force <- commitments %>%
    mutate(ZERO_DEFORESTATION_COMMITMENT = case_when(
      as.logical(HAS_COMMITMENT) %in% TRUE & START_YEAR <= year &
        (is.na(END_YEAR) | END_YEAR > year) ~ as.character(COMMITMENT_TYPE),
      TRUE ~ "NONE")) %>%
    select(EXPORTER_GROUP, ZERO_DEFORESTATION_COMMITMENT)
  if (anyDuplicated(in_force$EXPORTER_GROUP)) stop("company_commitments: one row per EXPORTER_GROUP, please")
  flows %>%
    left_join(in_force, by = "EXPORTER_GROUP") %>%
    mutate(ZERO_DEFORESTATION_COMMITMENT = if_else(is.na(ZERO_DEFORESTATION_COMMITMENT), "UNKNOWN",
                                                   ZERO_DEFORESTATION_COMMITMENT))
}

#' Run all steps.
#'
#' @param result     run_supply_chain_model() result
#' @param spatial    list from the country's read_spatial_inputs():
#'   production          REGION_ID, COCOA_PRODUCTION_KG (model year)
#'   region_metrics      see per_tonne_metrics()
#'   region_attributes   optional, see add_region_attributes()
#'   company_commitments optional, see add_company_commitments()
#' @return list(weights, per_tonne, flows)
run_exposure <- function(result, spatial, config) {
  if (config$year > config$cocoa_map_valid_until) {
    warning("Model year ", config$year, " is after ", config$cocoa_map_valid_until,
            ", the last export year the cocoa map can represent: cocoa deforestation ",
            "and degradation will miss recent cocoa expansion (docs/DEFORESTATION_METRICS.md).",
            call. = FALSE)
  }
  weights <- untraced_region_weights(result$output, spatial$production)
  per_tonne <- per_tonne_metrics(
    spatial$region_metrics,
    weights %>% transmute(REGION_ID, YEAR = config$year, SHARE_OF_UNTRACED_PRODUCTION),
    unknown_id = config$ids$unknown_region_id,
    indirect_id = config$ids$indirect_region_id)
  flows <- deforestation_exposure(result$output, per_tonne)
  if (!is.null(spatial$region_attributes)) flows <- add_region_attributes(flows, spatial$region_attributes)
  if (!is.null(spatial$company_commitments)) flows <- add_company_commitments(flows, spatial$company_commitments, config$year)
  list(weights = weights, per_tonne = per_tonne, flows = flows)
}
