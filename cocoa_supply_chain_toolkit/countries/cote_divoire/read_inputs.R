# =============================================================================
# Côte d'Ivoire: read the input files and put them in the standard format
# =============================================================================
# This is the ONLY place that knows Côte d'Ivoire's file names and column
# names. It returns the six tables described in docs/INPUT_DATA.md;
# everything after this is the same for every country.
#
# Files (relative to config$data_dir):
#   supplier_map/supplier_links_2024.csv     supplier-buyer links (standard format)
#   supplier_map/suppliers_2024.csv          suppliers, one row each (standard format)
#   licensed_buyers/licensed_buyers_2021.csv licensed cocoa buyers and their department
#   customs/cocoa_exports_2024.csv           customs export records
#   farm_survey/kit_farm_production.csv      farm production survey (KIT)
#   regions/departments.geojson              department boundaries
# =============================================================================

read_inputs <- function(config) {
  path <- function(...) {
    p <- file.path(config$data_dir, ...)
    if (!file.exists(p)) stop("Input file not found: ", p, call. = FALSE)
    p
  }

  # Supplier map: already in the standard format (built by
  # supplier_map/build_supplier_map_cote_divoire_2024.py, or by hand with the
  # spreadsheet template in supplier_map/templates/)
  supplier_links <- readr::read_csv(path("supplier_map", "supplier_links_2024.csv"),
                                    show_col_types = FALSE)
  suppliers <- readr::read_csv(path("supplier_map", "suppliers_2024.csv"), show_col_types = FALSE)

  # Licensed buyers (acheteurs agréés). The 2021 list is the latest available.
  licensed_buyers <- readr::read_delim(path("licensed_buyers", "licensed_buyers_2021.csv"),
                                       delim = ";", show_col_types = FALSE) %>%
    transmute(SHORT_NAME = NOM, COMPANY_NAME = DENOMINATION, REGION_CODE = LVL_4_CODE)

  # Customs export records (already cleaned, see input_preparation/trade/)
  trade <- readr::read_delim(path("customs", "cocoa_exports_2024.csv"),
                             delim = ";", show_col_types = FALSE,
                             col_types = readr::cols(HS6 = readr::col_character(),
                                                     HS_CODE = readr::col_character())) %>%
    mutate(NET_WEIGHT_KG = NET_WEIGHT_TON * 1000) %>%
    transmute(YEAR, COUNTRY_OF_ORIGIN, COUNTRY_OF_DESTINATION,
              EXPORTER, IMPORTER = BUYER,
              HS6, HS_CODE,
              NET_WEIGHT_KG,
              VALUE_USD = CIF_USD)

  # Farm production survey (KIT, Côte d'Ivoire farms)
  farm_production <- readr::read_delim(path("farm_survey", "kit_farm_production.csv"),
                                       delim = ";", show_col_types = FALSE) %>%
    transmute(FARM_PRODUCTION_KG = cocoa_prod_total_kgs)

  # Department boundaries (only codes and names are needed by the model)
  regions <- sf::read_sf(path("regions", "departments.geojson")) %>%
    sf::st_drop_geometry() %>%
    transmute(REGION_CODE = LVL_4_CODE, REGION_NAME = LVL_4_NAME)

  list(supplier_links = supplier_links, suppliers = suppliers,
       licensed_buyers = licensed_buyers, trade = trade,
       farm_production = farm_production, regions = regions)
}


# =============================================================================
# Inputs of the deforestation-exposure step (model/R/deforestation_exposure.R)
# =============================================================================
# Files (in config$data_dir/deforestation_metrics/), all keyed by REGION_ID
# (e.g. "CI-030102"), the same IDs as REGION_ID in the model output:
#   cocoa_deforestation_by_region.csv  cocoa deforestation and degradation (ha)
#       and emissions (t CO2) per region and year, written by
#       deforestation_metrics/reshape_earth_engine_exports.py
#   cocoa_production_by_region.csv     cocoa production per region and year (t)
#   cocoa_area_by_region.csv           cocoa area per region (ha)
#   region_attributes.csv              optional: e.g. the ecoregion of each region
#   company_commitments.csv            optional: exporters' zero-deforestation commitments
# (Production and area come from the Earth Engine script, sections B and C,
# or from national statistics.)
# =============================================================================

read_spatial_inputs <- function(config) {
  path <- function(f) file.path(config$data_dir, "deforestation_metrics", f)
  read <- function(f) {
    if (!file.exists(path(f))) stop("Input file not found: ", path(f), call. = FALSE)
    readr::read_csv(path(f), show_col_types = FALSE)
  }
  read_optional <- function(f) if (file.exists(path(f))) readr::read_csv(path(f), show_col_types = FALSE)

  metrics    <- read("cocoa_deforestation_by_region.csv")
  production <- read("cocoa_production_by_region.csv")
  area       <- read("cocoa_area_by_region.csv")

  if (!config$year %in% metrics$YEAR) {
    stop("The deforestation metrics have no rows for ", config$year, call. = FALSE)
  }

  list(
    # production in the model year, used to weight untraced cocoa by region
    production = production %>%
      filter(YEAR == config$year) %>%
      transmute(REGION_ID, COCOA_PRODUCTION_KG = COCOA_TONNES * 1000),
    # one row per region and year: metrics, production (t) and cocoa area (ha)
    region_metrics = metrics %>%
      inner_join(production, by = c("REGION_ID", "YEAR")) %>%
      left_join(area, by = "REGION_ID"),
    region_attributes = read_optional("region_attributes.csv"),
    company_commitments = read_optional("company_commitments.csv")
  )
}
