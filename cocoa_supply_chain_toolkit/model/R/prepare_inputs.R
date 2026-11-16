# =============================================================================
# prepare_inputs.R: turn the country's raw tables into model inputs
# =============================================================================
# Each country supplies a read_inputs() function (countries/<country>/
# read_inputs.R) that returns six tables in the standard format described in
# docs/INPUT_DATA.md. prepare_inputs() below then does the processing that is
# the same for every country:
#   - gives every supplier (cooperative / licensed buyer) a stable ID
#   - fixes column types
#   - cleans and groups company names (see company_names.R)
#   - converts traded weight to bean-equivalent weight
#   - drops excluded products (cocoa shells/waste)
# =============================================================================

#' Check that a table has the required columns; stop with a clear message if not.
require_columns <- function(df, cols, table_name) {
  missing <- setdiff(cols, names(df))
  if (length(missing) > 0) {
    stop("Table '", table_name, "' is missing column(s): ", paste(missing, collapse = ", "),
         "\nSee docs/INPUT_DATA.md for the expected format.", call. = FALSE)
  }
  invisible(df)
}

make_supplier_id <- function(number, prefix, width) {
  paste0(prefix, stringr::str_pad(number, width = width, pad = "0"))
}

#' Supplier-buyer links (one row per link between a supplier and a company
#' that discloses buying from it).
#'
#' Company names (BUYER, TRADER_NAME) are put through the same group-name
#' rules as the customs data (standardise_buyer_names), so that "OFI" in a
#' disclosure matches "OLAM" in customs.
prepare_supplier_links <- function(links_raw, config) {
  require_columns(links_raw, c("SUPPLIER_NUMBER", "YEAR", "REGION_CODE", "SUPPLIER_SHORT_NAME",
                               "SUPPLIER_NAME", "BUYER", "BUYER_IS_TRADER", "NUMBER_OF_FARMERS",
                               "CERTIFICATIONS", "CERTIFIED", "LINK_ID", "DISCLOSED_BY"), "supplier_links")
  links_raw %>%
    filter(YEAR == config$year) %>%
    mutate(across(c(REGION_CODE, SUPPLIER_SHORT_NAME, SUPPLIER_NAME, BUYER, CERTIFICATIONS,
                    LINK_ID, DISCLOSED_BY), as.character)) %>%
    # names used inside the model steps (model_steps.R)
    transmute(COOP_ID = as.integer(SUPPLIER_NUMBER),
              GEOCODE = REGION_CODE,
              COOPACRONYM = SUPPLIER_SHORT_NAME,
              COOPNAME = SUPPLIER_NAME,
              TRADER_NAME = if_else(as.logical(BUYER_IS_TRADER) %in% TRUE, BUYER, NA_character_),
              BUYER,
              NUM_FARMERS = NUMBER_OF_FARMERS,
              CERTIFICATIONS, CERTIFIED,
              FLOW_ID = LINK_ID,
              DISCLOSURE_SOURCE = DISCLOSED_BY) %>%
    mutate(SUPPLIER_ID = make_supplier_id(COOP_ID, config$ids$cooperative_prefix,
                                          config$ids$cooperative_width)) %>%
    select(SUPPLIER_ID, COOP_ID, GEOCODE, COOPACRONYM, COOPNAME, TRADER_NAME, BUYER,
           NUM_FARMERS, CERTIFICATIONS, CERTIFIED, FLOW_ID, DISCLOSURE_SOURCE) %>%
    mutate(
      COOP_ID = as.integer(COOP_ID),
      NUM_FARMERS = as.integer(NUM_FARMERS),
      CERTIFIED = as.logical(CERTIFIED)
    ) %>%
    standardise_buyer_names(config$rules$company_groups)
}

#' Give every supplier link ONE buyer, named as in the customs data.
#'
#' 1. Split combined buyers. A link whose BUYER lists several companies
#'    ("BARRY CALLEBAUT + CARGILL") becomes one link per company, each with
#'    the link's farmer number, certification and so on. (Combined names come
#'    from cooperative-level summaries, where all buyers of a cooperative are
#'    joined with " + ".) If BUYER was a trader, each company is a trader too.
#' 2. Group names. BUYER and TRADER_NAME go through company_group(), the
#'    cleaning used for exporters and importers in customs data.
#' 3. One link per supplier and buyer. After steps 1-2 a supplier can have two
#'    links to the same buyer (e.g. "OFI" and "OLAM" both become OLAM). One is
#'    kept: a link disclosed on its own before one split from a combined name,
#'    then one with a farmer number, then the first in the file. TRADER_NAME
#'    is kept if any of the duplicates had it.
#' Links with no buyer are left as they are.
standardise_buyer_names <- function(links, group_rules, separator = " + ") {
  links %>%
    mutate(link_row_ = row_number(),
           combined_ = !is.na(BUYER) & grepl(separator, BUYER, fixed = TRUE),
           was_trader_ = !is.na(TRADER_NAME)) %>%
    # 1. split combined buyers
    tidyr::separate_longer_delim(BUYER, delim = separator) %>%
    group_by(link_row_) %>%
    mutate(FLOW_ID = if (n() > 1) paste0(FLOW_ID, "-", row_number()) else FLOW_ID) %>%
    ungroup() %>%
    mutate(BUYER = stringr::str_squish(BUYER),
           TRADER_NAME = if_else(combined_ & was_trader_, BUYER, TRADER_NAME),
           # 2. same names as customs
           BUYER = company_group(BUYER, group_rules),
           TRADER_NAME = company_group(TRADER_NAME, group_rules)) %>%
    # 3. one link per supplier and buyer
    mutate(no_buyer_ = is.na(BUYER)) %>%
    group_by(SUPPLIER_ID, BUYER, no_buyer_) %>%
    mutate(keep_ = no_buyer_ | row_number(paste(combined_, is.na(NUM_FARMERS), sprintf("%09d", link_row_))) == 1,
           TRADER_NAME = if (n() > 1 && any(was_trader_) && !first(no_buyer_)) BUYER else TRADER_NAME) %>%
    ungroup() %>%
    filter(keep_) %>%
    arrange(link_row_) %>%
    select(-link_row_, -combined_, -was_trader_, -no_buyer_, -keep_)
}

#' Suppliers, one row each (used to locate cooperatives that export directly).
prepare_suppliers <- function(suppliers_raw, config) {
  require_columns(suppliers_raw, c("SUPPLIER_NUMBER", "YEAR", "REGION_CODE", "SUPPLIER_SHORT_NAME",
                                   "SUPPLIER_NAME", "CERTIFICATIONS", "CERTIFIED"), "suppliers")
  suppliers_raw %>%
    filter(YEAR == config$year) %>%
    mutate(across(c(REGION_CODE, SUPPLIER_SHORT_NAME, SUPPLIER_NAME, CERTIFICATIONS), as.character)) %>%
    transmute(COOP_ID = as.integer(SUPPLIER_NUMBER), YEAR,
              GEOCODE = REGION_CODE, COOPACRONYM = SUPPLIER_SHORT_NAME, COOPNAME = SUPPLIER_NAME,
              CERTIFICATIONS, CERTIFIED = as.logical(CERTIFIED)) %>%
    mutate(SUPPLIER_ID = make_supplier_id(COOP_ID, config$ids$cooperative_prefix,
                                          config$ids$cooperative_width))
}

#' Licensed buyers / registered intermediaries with a known location.
#' IDs are numbered in alphabetical order of (name, company name, region).
prepare_licensed_buyers <- function(licensed_buyers_raw, config) {
  require_columns(licensed_buyers_raw, c("SHORT_NAME", "COMPANY_NAME", "REGION_CODE"), "licensed_buyers")
  licensed_buyers_raw %>%
    transmute(COOPACRONYM = as.character(SHORT_NAME), COOPNAME = as.character(COMPANY_NAME),
              GEOCODE = as.character(REGION_CODE)) %>%
    arrange(COOPACRONYM, COOPNAME, GEOCODE) %>%
    group_by(COOPACRONYM, COOPNAME, GEOCODE) %>%
    mutate(SUPPLIER_ID = make_supplier_id(cur_group_id(), config$ids$licensed_buyer_prefix,
                                          config$ids$licensed_buyer_width)) %>%
    ungroup() %>%
    mutate(FLOW_ID = SUPPLIER_ID) %>%
    select(SUPPLIER_ID, GEOCODE, COOPACRONYM, COOPNAME, FLOW_ID)
}

#' Read the bean-equivalence factor table (HS6 -> factor).
read_bean_equivalence <- function(path) {
  cef <- readr::read_delim(path, delim = ";",
                           col_types = readr::cols(HS6 = readr::col_character(),
                                                   EQ_FACTOR = readr::col_double(),
                                                   .default = readr::col_character())) %>%
    dplyr::select(HS6, EQ_FACTOR)
  stopifnot(cef %>% group_by(HS6) %>% count() %>% ungroup() %>% pull(n) %>% max() == 1)
  cef
}

#' Customs export records: clean names, convert to bean equivalents.
prepare_trade <- function(trade_raw, bean_equivalence, config) {
  require_columns(trade_raw, c("YEAR", "COUNTRY_OF_ORIGIN", "COUNTRY_OF_DESTINATION",
                               "EXPORTER", "IMPORTER", "HS6", "HS_CODE",
                               "NET_WEIGHT_KG", "VALUE_USD"), "trade")
  trade <- trade_raw %>%
    clean_trade_names(config) %>%
    left_join(bean_equivalence, by = "HS6") %>%
    mutate(BEAN_EQUIVALENT_VOLUME = EQ_FACTOR * NET_WEIGHT_KG) %>%
    dplyr::select(-EQ_FACTOR) %>%
    filter(!HS6 %in% config$commodity$excluded_hs6) %>%
    rename(VOLUME_RAW = NET_WEIGHT_KG,
           PRODUCT_B_CODE = HS_CODE) %>%
    select(YEAR, COUNTRY_OF_ORIGIN, COUNTRY_OF_DESTINATION,
           EXPORTER_ORIGINAL, EXPORTER_CLEAN, EXPORTER_GROUP_CLEAN, HS6, PRODUCT_B_CODE,
           VOLUME_RAW, BEAN_EQUIVALENT_VOLUME,
           VALUE_USD,
           IMPORTER_ORIGINAL, IMPORTER_GROUP_CLEAN)
  if (anyNA(trade$BEAN_EQUIVALENT_VOLUME)) {
    stop("Some HS6 codes in the trade data have no bean-equivalence factor: ",
         paste(unique(trade$HS6[is.na(trade$BEAN_EQUIVALENT_VOLUME)]), collapse = ", "))
  }
  trade
}

#' Run all preparation steps. `raw` is the list returned by the country's
#' read_inputs(); the result is the list of model inputs used by run_supply_chain_model().
prepare_inputs <- function(raw, config) {
  bean_equivalence <- read_bean_equivalence(config$commodity$bean_equivalence_file)
  require_columns(raw$farm_production, "FARM_PRODUCTION_KG", "farm_production")
  require_columns(raw$regions, c("REGION_CODE", "REGION_NAME"), "regions")
  list(
    supplier_links   = prepare_supplier_links(raw$supplier_links, config),
    suppliers        = prepare_suppliers(raw$suppliers, config),
    licensed_buyers  = prepare_licensed_buyers(raw$licensed_buyers, config),
    trade            = prepare_trade(raw$trade, bean_equivalence, config),
    bean_equivalence = bean_equivalence,
    farm_production  = raw$farm_production %>% transmute(PRODUCTION_KG = FARM_PRODUCTION_KG),
    regions          = raw$regions
  )
}
