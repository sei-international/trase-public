# =============================================================================
# summarise_results.R: summarise Monte Carlo draws and format the output table
# =============================================================================

#' Product names from HS codes: the 4-digit HS heading decides the product.
product_names_from_hs6 <- function(hs6, config) {
  hs6 <- unique(hs6)
  hs6 <- hs6[grepl(paste0("^", config$commodity$hs_chapter_prefix), hs6)]
  names_by_hs4 <- config$commodity$product_names_by_hs4
  product_names <- tibble(HS6 = hs6,
                          PRODUCT = unname(names_by_hs4[substr(hs6, 1, 4)])) %>%
    distinct(HS6, PRODUCT) %>%
    mutate(COMMODITY = config$commodity$name)
  if (any(is.na(product_names$PRODUCT))) {
    stop("No product name for HS6 code(s): ",
         paste(product_names$HS6[is.na(product_names$PRODUCT)], collapse = ", "),
         ". Add the HS4 heading to commodity$product_names_by_hs4.")
  }
  product_names
}

#' Collapse draws to means, add names and IDs, label untraced volume as
#' INDIRECT (exporter disclosed something) or UNKNOWN (exporter disclosed
#' nothing), and return the output table.
finalise_output <- function(flows, trade, regions, bean_equivalence, config) {
  ids <- config$ids
  region_to_id <- config$region_to_id

  flows_long <- flows %>%
    rename(EXPORTER_GROUP_CLEAN = BUYER,
           GEOCODE_COCOA = GEOCODE) %>%
    mutate(COUNTRY_OF_ORIGIN = config$country_name,
           HS6 = substr(PRODUCT_B_CODE, 0, 6),
           GEOCODE_PROVIDER = GEOCODE_COCOA) %>%
    select(YEAR, GEOCODE_COCOA, GEOCODE_PROVIDER, SUPPLIER_ID, COOPACRONYM_AANAME, COOPNAME_AADENOMINATION, FLOW_ID,
           EXPORTER_ORIGINAL, EXPORTER_GROUP_CLEAN, COUNTRY_OF_ORIGIN, COUNTRY_OF_DESTINATION, HS6, PRODUCT_B_CODE,
           CERTIFICATIONS, CERTIFIED,
           COOP_SOURCED_DIRECT_VOLUME_BEQ_distribution,
           COOP_SOURCED_DIRECT_VAL_distribution)

  region_names <- bind_cols(LVL_4_CODE = regions$REGION_CODE, LVL_4_NAME = regions$REGION_NAME) %>%
    bind_rows(c(LVL_4_CODE = "UNKNOWN", LVL_4_NAME = "UNKNOWN"))

  product_names <- product_names_from_hs6(trade$HS6, config)

  out <- flows_long %>%
    rowwise() %>%
    mutate(
      MEAN_COOP_SOURCED_DIRECT_VOLUME_BEQ =
        mean(unlist(COOP_SOURCED_DIRECT_VOLUME_BEQ_distribution$COOP_SOURCED_DIRECT_VOLUME_BEQ)),
      MEAN_COOP_SOURCED_DIRECT_VAL =
        mean(unlist(COOP_SOURCED_DIRECT_VAL_distribution$COOP_SOURCED_DIRECT_VAL))
    ) %>%
    left_join(bean_equivalence, by = "HS6") %>%
    mutate(MEAN_COOP_SOURCED_DIRECT_VOLUME_RAW = MEAN_COOP_SOURCED_DIRECT_VOLUME_BEQ / EQ_FACTOR) %>%
    dplyr::select(-EQ_FACTOR) %>%
    left_join(region_names, by = c("GEOCODE_COCOA" = "LVL_4_CODE")) %>%
    left_join(trade %>% distinct(EXPORTER_ORIGINAL, EXPORTER_CLEAN), by = "EXPORTER_ORIGINAL") %>%
    left_join(product_names, by = "HS6") %>%
    mutate(
      GEOCODE_COCOA = region_to_id(GEOCODE_COCOA),
      GEOCODE_PROVIDER = region_to_id(GEOCODE_PROVIDER),
      LOGISTICS_HUB_COOP = gsub(pattern = "UNKNOWN", replacement = ids$unknown_supplier_id, SUPPLIER_ID)
    ) %>%
    select(-COOP_SOURCED_DIRECT_VOLUME_BEQ_distribution,
           -COOP_SOURCED_DIRECT_VAL_distribution) %>%
    select(
      COUNTRY_OF_ORIGIN,
      COUNTRY_OF_DESTINATION,
      ORIGIN = LVL_4_NAME,
      EXPORTER = EXPORTER_ORIGINAL,
      EXPORTER_CLEAN,
      EXPORTER_GROUP_CLEAN,
      YEAR,
      HS6,
      PRODUCT_B_CODE,
      VOLUME_RAW = MEAN_COOP_SOURCED_DIRECT_VOLUME_RAW,
      VOLUME_BEAN_EQUIVALENT = MEAN_COOP_SOURCED_DIRECT_VOLUME_BEQ,
      VALUE = MEAN_COOP_SOURCED_DIRECT_VAL,
      REGION_ID = GEOCODE_COCOA,
      REGION_NAME = LVL_4_NAME,
      PRODUCT,
      COMMODITY,
      LOGISTICS_HUB_COOP,
      COOPACRONYM = COOPACRONYM_AANAME,
      COOPNAME = COOPNAME_AADENOMINATION
    )

  if (anyNA(out$VOLUME_RAW) | anyNA(out$VOLUME_BEAN_EQUIVALENT) | anyNA(out$VALUE)) {
    stop("unexpected missing values in flows")
  }

  # INDIRECT vs UNKNOWN: untraced volume of exporters that disclosed at least
  # one supplier is "indirect sourcing"; the rest stays "unknown"
  transparent_traders <- out %>%
    filter(REGION_ID != ids$unknown_region_id) %>%
    distinct(EXPORTER_GROUP_CLEAN) %>%
    pull(EXPORTER_GROUP_CLEAN)

  out <- out %>%
    ungroup() %>%
    mutate(
      REGION_ID = case_when(
        REGION_ID == ids$unknown_region_id & EXPORTER_GROUP_CLEAN %in% transparent_traders ~ ids$indirect_region_id,
        TRUE ~ REGION_ID),
      REGION_NAME = case_when(
        REGION_NAME == "UNKNOWN" & EXPORTER_GROUP_CLEAN %in% transparent_traders ~ "INDIRECT SOURCING",
        TRUE ~ REGION_NAME)
    )

  # Rows with zero volume: the indirect part of exporters whose direct volume
  # equals all their exports. They carry no information.
  out <- out %>% filter(VOLUME_BEAN_EQUIVALENT > 0)

  out <- out %>%
    mutate(COOPNAME = case_when(is.na(COOPNAME) ~ "UNKNOWN COOPERATIVE NAME", TRUE ~ COOPNAME))

  # Name the value column as the country's customs data report it (e.g. CIF_USD)
  names(out)[names(out) == "VALUE"] <- config$value_column_name
  list(output = out, flows_long = flows_long)
}

#' Share of exported volume that is direct / indirect / unknown (percent).
sourcing_summary <- function(output) {
  output %>%
    mutate(SOURCING = case_when(
      !REGION_NAME %in% c("UNKNOWN", "INDIRECT SOURCING") ~ "DIRECT SOURCING",
      TRUE ~ REGION_NAME)) %>%
    mutate(TOTAL = sum(VOLUME_BEAN_EQUIVALENT)) %>%
    group_by(SOURCING) %>%
    summarise(PERCENT_OF_VOLUME = sum(VOLUME_BEAN_EQUIVALENT) / unique(TOTAL) * 100)
}

#' Plain-language column names for the output table.
#' (Inside the model steps, columns keep shorter working names; this is the
#' only place where they are translated. See docs/GLOSSARY.md.)
OUTPUT_COLUMN_NAMES <- c(
  EXPORTER_NAME_CLEANED = "EXPORTER_CLEAN",
  EXPORTER_GROUP        = "EXPORTER_GROUP_CLEAN",
  HS_CODE               = "PRODUCT_B_CODE",
  PRODUCT_WEIGHT_KG     = "VOLUME_RAW",
  BEAN_EQUIVALENT_KG    = "VOLUME_BEAN_EQUIVALENT",
  SUPPLIER_ID           = "LOGISTICS_HUB_COOP",
  SUPPLIER_SHORT_NAME   = "COOPACRONYM",
  SUPPLIER_NAME         = "COOPNAME"
)

#' Final output table with plain column names, plus SOURCING_TYPE
#' (DIRECT / INDIRECT / UNKNOWN).
plain_output <- function(output, config) {
  output %>%
    mutate(SOURCING_TYPE = case_when(
      REGION_ID == config$ids$unknown_region_id ~ "UNKNOWN",
      REGION_ID == config$ids$indirect_region_id ~ "INDIRECT",
      TRUE ~ "DIRECT")) %>%
    select(-ORIGIN) %>%
    rename(all_of(OUTPUT_COLUMN_NAMES)) %>%
    relocate(SOURCING_TYPE, .before = REGION_ID)
}

#' Every Monte Carlo draw per flow, with plain column names. The draws are
#' in list columns (one tibble of N_DRAWS values per row).
plain_draws <- function(flows_long) {
  flows_long %>%
    select(-GEOCODE_PROVIDER) %>%
    rename(REGION_CODE = GEOCODE_COCOA,
           SUPPLIER_SHORT_NAME = COOPACRONYM_AANAME,
           SUPPLIER_NAME = COOPNAME_AADENOMINATION,
           LINK_ID = FLOW_ID,
           EXPORTER = EXPORTER_ORIGINAL,
           EXPORTER_GROUP = EXPORTER_GROUP_CLEAN,
           HS_CODE = PRODUCT_B_CODE,
           BEAN_EQUIVALENT_KG_DRAWS = COOP_SOURCED_DIRECT_VOLUME_BEQ_distribution,
           VALUE_USD_DRAWS = COOP_SOURCED_DIRECT_VAL_distribution)
}
