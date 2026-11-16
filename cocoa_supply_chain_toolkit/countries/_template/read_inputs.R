# =============================================================================
# <COUNTRY>: read the input files and put them in the standard format (TEMPLATE)
# =============================================================================
# Return a list of six tables with EXACTLY these column names. Types and
# meanings are in docs/INPUT_DATA.md. Only read, rename and select here; all
# processing that is the same for every country happens later, in
# model/R/prepare_inputs.R.
# countries/cote_divoire/read_inputs.R is a complete example.
#
# Replace every TODO_... file name with your own file.
# =============================================================================

read_inputs <- function(config) {
  path <- function(...) {
    p <- file.path(config$data_dir, ...)
    if (!file.exists(p)) stop("Input file not found: ", p, call. = FALSE)
    p
  }

  # 1 and 2. The supplier map. If you filled in the spreadsheet template
  # (supplier_map/templates/supplier_map_template.xlsx), read its two sheets
  # directly; the columns are already right. Otherwise read your own files and
  # rename their columns to the ones listed in docs/INPUT_DATA.md.
  supplier_map_file <- path("TODO_supplier_map.xlsx")
  supplier_links <- readxl::read_excel(supplier_map_file, sheet = "supplier_links")
  suppliers      <- readxl::read_excel(supplier_map_file, sheet = "suppliers")

  # 3. Licensed buyers / registered intermediaries with a known region.
  #    If your country has none, return an empty table with these columns:
  licensed_buyers <- tibble::tibble(SHORT_NAME = character(), COMPANY_NAME = character(),
                                    REGION_CODE = character())

  # 4. Customs export records: one row per shipment
  trade <- readr::read_csv(path("TODO_customs_exports.csv"), show_col_types = FALSE,
                           col_types = readr::cols(HS6 = "c", HS_CODE = "c")) %>%
    transmute(YEAR, COUNTRY_OF_ORIGIN, COUNTRY_OF_DESTINATION,
              EXPORTER,          # exporter name as in customs
              IMPORTER,          # foreign buyer name as in customs (NA if not reported)
              HS6,               # 6-digit HS code, text
              HS_CODE,           # most detailed product code available, text
              NET_WEIGHT_KG,     # net weight in kg
              VALUE_USD)         # value in USD (CIF or FOB; see config$value_column_name)

  # 5. Farm production survey: total cocoa production per surveyed farm (kg/year)
  farm_production <- readr::read_csv(path("TODO_farm_production.csv"), show_col_types = FALSE) %>%
    transmute(FARM_PRODUCTION_KG)

  # 6. Regions: codes and names of the sub-national units
  regions <- sf::read_sf(path("TODO_regions.geojson")) %>%
    sf::st_drop_geometry() %>%
    transmute(REGION_CODE, REGION_NAME)

  list(supplier_links = supplier_links, suppliers = suppliers,
       licensed_buyers = licensed_buyers, trade = trade,
       farm_production = farm_production, regions = regions)
}


# =============================================================================
# Inputs of the deforestation-exposure step (optional;
# model/R/deforestation_exposure.R)
# =============================================================================
# Delete this function if you only want the supply-chain model. REGION_ID must
# be the same as REGION_ID in the model output, i.e. the result of
# config$region_to_id(). The formats are in docs/INPUT_DATA.md, section 7.
# =============================================================================

read_spatial_inputs <- function(config) {
  path <- function(...) {
    p <- file.path(config$data_dir, ...)
    if (!file.exists(p)) stop("Input file not found: ", p, call. = FALSE)
    p
  }
  # Output of deforestation_metrics/reshape_earth_engine_exports.py:
  # REGION_ID, YEAR, COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL,
  # COCOA_DEFORESTATION_AND_DEGRADATION_ANNUAL, COCOA_GROSS_EMISSIONS_*, COCOA_NET_EMISSIONS_*
  metrics <- readr::read_csv(path("TODO_cocoa_deforestation_by_region.csv"), show_col_types = FALSE)
  # REGION_ID, YEAR, COCOA_TONNES (production in tonnes)
  production <- readr::read_csv(path("TODO_cocoa_production_by_region.csv"), show_col_types = FALSE)
  # REGION_ID, COCOA_HA (cocoa area in hectares)
  area <- readr::read_csv(path("TODO_cocoa_area_by_region.csv"), show_col_types = FALSE)

  list(
    production = production %>%
      filter(YEAR == config$year) %>%
      transmute(REGION_ID, COCOA_PRODUCTION_KG = COCOA_TONNES * 1000),
    region_metrics = metrics %>%
      inner_join(production, by = c("REGION_ID", "YEAR")) %>%
      left_join(area, by = "REGION_ID"),
    # Optional extras (delete the line if you do not have them):
    # region_attributes: REGION_ID plus any columns, e.g. ECOREGION
    region_attributes = NULL,
    # company_commitments: EXPORTER_GROUP, HAS_COMMITMENT, COMMITMENT_TYPE, START_YEAR, END_YEAR
    company_commitments = NULL
  )
}
