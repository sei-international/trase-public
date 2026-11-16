# =============================================================================
# model_steps.R: the supply-chain model, one function per step
# =============================================================================
# Links each export flow (exporter x destination x product) to the suppliers
# (cooperatives, licensed buyers) and sub-national regions it was sourced from.
# docs/HOW_THE_MODEL_WORKS.md explains every step in plain language; the step numbers in
# the function names below match that document.
#
# All country-specific choices come from `config` (countries/<country>/config.R).
# tests/test_model_results.R checks that the results stay as expected after
# any change to this file.
#
# Monte Carlo representation
# --------------------------
# Uncertain quantities are carried as N_DRAWS values per row. They are stored
# in "nested" list-columns named <NAME>_distribution, each holding a small
# table with the value (<NAME>) and the draw number (NUM_<NAME>). The functions
# unnest them to compute, then nest them again to keep tables small.
# =============================================================================

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#' Stop if two totals differ by more than 0.01% (used after each step to check
#' that no volume or value has been lost or created).
check_total <- function(expected, actual, what = "total") {
  if (!isTRUE(all.equal(expected, actual, tolerance = 0.0001))) {
    stop("Consistency check failed for ", what, ": expected ", expected, ", got ", actual,
         call. = FALSE)
  }
  invisible(TRUE)
}

#' Sum, over rows, of the mean across draws of a nested distribution column.
sum_of_means <- function(df, dist_col, value_col) {
  df %>%
    rowwise() %>%
    mutate(MEAN = mean(unlist(.data[[dist_col]][[value_col]]))) %>%
    drop_na(MEAN) %>%
    pull(MEAN) %>%
    sum()
}

#' Is this exporter group a cooperative (or union of cooperatives) exporting directly?
is_exporting_coop <- function(group_name, config) {
  grepl(config$exporting_cooperative_tag, group_name, fixed = TRUE) |
    group_name %in% config$cooperative_unions
}

# ---------------------------------------------------------------------------
# Step 0.1: re-attribute shipments using the importer; flag shipments that
#           can contain directly sourced (traceable) volume
# ---------------------------------------------------------------------------
step01_attribute_shipments <- function(trade, supplier_links, config) {
  exporter_groups <- trade$EXPORTER_GROUP_CLEAN
  disclosing_buyers <- supplier_links$BUYER[!(supplier_links$BUYER %in% config$cooperative_unions)]

  trade %>%
    mutate(
      EXP_EQ_IMP = EXPORTER_GROUP_CLEAN == IMPORTER_GROUP_CLEAN,

      # Did the exporter disclose suppliers? (unions of cooperatives are treated
      # as exporting cooperatives, not as disclosing exporters)
      EXP_DISCL = EXPORTER_GROUP_CLEAN %in% disclosing_buyers,
      # Is the importer a disclosing TRADER?
      IMP_DISCL_TRADER = IMPORTER_GROUP_CLEAN %in% supplier_links$TRADER_NAME,
      # Is the importer a signatory of a sector commitment (e.g. Cocoa & Forests
      # Initiative) that also exports from the country itself?
      IMP_CFI_TRADER = IMPORTER_GROUP_CLEAN %in% config$commitment_signatories &
        IMPORTER_GROUP_CLEAN %in% exporter_groups,

      IS_EXP_COOP = is_exporting_coop(EXPORTER_GROUP_CLEAN, config),

      # Shipments from a non-disclosing exporter to a disclosing (or committed)
      # importer are counted under the importer.
      EXPORTER_GROUP_CLEAN = case_when(
        !EXP_DISCL & (IMP_DISCL_TRADER | IMP_CFI_TRADER) ~ IMPORTER_GROUP_CLEAN,
        TRUE ~ EXPORTER_GROUP_CLEAN
      ),

      # Only shipments whose exporter disclosed, or that were exported by a
      # cooperative, can contain directly sourced volume.
      POTENTIAL_DIRECT_VOL = case_when(
        EXP_DISCL | IS_EXP_COOP ~ BEAN_EQUIVALENT_VOLUME,
        TRUE ~ 0
      ),
      POTENTIAL_DIRECT_VAL = case_when(
        EXP_DISCL | IS_EXP_COOP ~ VALUE_USD,
        TRUE ~ 0
      )
    )
}

#' Total exported volume (bean equivalent) and value per exporter group.
summarise_exporters <- function(trade) {
  list(
    volume = trade %>%
      group_by(YEAR, EXPORTER_GROUP_CLEAN) %>%
      summarise(TRADER_BEQ_VOLUME_EXPORTED = sum(BEAN_EQUIVALENT_VOLUME),
                TRADER_BEQ_VOLUME_EXPORTED_CAPPED = sum(POTENTIAL_DIRECT_VOL),
                .groups = "drop_last") %>%
      ungroup(),
    value = trade %>%
      group_by(YEAR, EXPORTER_GROUP_CLEAN) %>%
      summarise(VALUE_USD = sum(VALUE_USD),
                TRADER_VALUE_USD_EXPORTED_CAPPED = sum(POTENTIAL_DIRECT_VAL),
                .groups = "drop_last") %>%
      ungroup()
  )
}

# ---------------------------------------------------------------------------
# Steps 1-4: list every supplier link, plus one UNKNOWN link per exporter
# ---------------------------------------------------------------------------

#' Steps 1-2: keep links that have a buyer.
step02_disclosed_links <- function(supplier_links) {
  supplier_links %>% filter(!is.na(BUYER))
}

#' Step 3: licensed buyers whose name matches an exporter in customs data.
step03_licensed_buyer_links <- function(licensed_buyers, trade, config) {
  extra <- config$licensed_buyer_to_exporter   # named vector: buyer name -> exporter group
  licensed_buyers %>%
    rename(COOPACRONYM_AANAME = COOPACRONYM,
           COOPNAME_AADENOMINATION = COOPNAME) %>%
    filter(COOPNAME_AADENOMINATION %in% c(trade$EXPORTER_CLEAN, trade$EXPORTER_GROUP_CLEAN)) %>%
    mutate(BUYER = case_when(
      COOPNAME_AADENOMINATION %in% trade$EXPORTER_GROUP_CLEAN ~
        trade$EXPORTER_GROUP_CLEAN[match(COOPNAME_AADENOMINATION, trade$EXPORTER_GROUP_CLEAN)],
      COOPNAME_AADENOMINATION %in% names(extra) ~ unname(extra[COOPNAME_AADENOMINATION]),
      TRUE ~ NA_character_
    ))
}

#' Step 4: combine disclosed links, licensed-buyer links and one UNKNOWN link
#' per exporter (which will later hold all volume that cannot be traced).
step04_combine_links <- function(disclosed_links, licensed_buyer_links, trade) {
  disclosed_links <- disclosed_links %>%
    rename(COOPACRONYM_AANAME = COOPACRONYM,
           COOPNAME_AADENOMINATION = COOPNAME)

  unknown_links <- tibble(BUYER = unique(trade$EXPORTER_GROUP_CLEAN)) %>%
    mutate(SUPPLIER_ID = "UNKNOWN",
           FLOW_ID = "UNKNOWN",
           GEOCODE = "UNKNOWN",
           COOPACRONYM_AANAME = "UNKNOWN",
           COOPNAME_AADENOMINATION = "UNKNOWN")

  # GEOCODE == "UNKNOWN" marks both indirect and unknown sourcing until the
  # final step. Links whose location is missing are dropped.
  list(
    supplier_links = disclosed_links,
    links = bind_rows(disclosed_links, licensed_buyer_links, unknown_links) %>%
      filter(!is.na(GEOCODE))
  )
}

# ---------------------------------------------------------------------------
# Step 5: number of farmers per link (N_DRAWS values per link)
# ---------------------------------------------------------------------------
step05_farmers_per_link <- function(links, disclosed_links, n_draws) {
  # Pool of disclosed sizes to sample from (links to traders only; 0s excluded)
  farmer_disclosures <- na.omit(disclosed_links %>%
                                  mutate(NUM_FARMERS = na_if(disclosed_links$NUM_FARMERS, 0)) %>%
                                  filter(!is.na(TRADER_NAME)) %>%
                                  select(NUM_FARMERS))

  links %>%
    # disclosures of 0 farmers are credible but cannot carry volume: drop them
    filter(NUM_FARMERS > 0 | is.na(NUM_FARMERS)) %>%
    mutate(NUM_FARMERS = case_when(
      GEOCODE == "UNKNOWN" ~ 0,
      TRUE ~ as.double(NUM_FARMERS)
    )) %>%
    rowwise() %>%
    mutate(NUM_FARMERS_list = case_when(
      # size unknown: draw from the disclosed sizes
      is.na(NUM_FARMERS) ~ list(sample(farmer_disclosures$NUM_FARMERS, size = n_draws, replace = TRUE)),
      # size disclosed (or imputed upstream): same value in every draw
      TRUE ~ list(rep(NUM_FARMERS, n_draws))
    )) %>%
    unnest(cols = c(NUM_FARMERS_list)) %>%
    group_by() %>%
    nest(NUM_FARMERS_list = NUM_FARMERS_list) %>%
    ungroup() %>%
    mutate(NUM_FARMERS_distribution = map(NUM_FARMERS_list, ~ .x %>%
                                            mutate(NUM_NUM_FARMERS_est = row.names(.)) %>%
                                            rename(NUM_FARMERS_est = NUM_FARMERS_list))) %>%
    select(-NUM_FARMERS_list)
}

# ---------------------------------------------------------------------------
# Step 6: each link's share of its buyer's total farmers
# ---------------------------------------------------------------------------
step06_link_shares <- function(links) {
  farmers_per_trader <- links %>%
    unnest(NUM_FARMERS_distribution) %>%
    group_by(BUYER, NUM_NUM_FARMERS_est) %>%
    summarise(TOTAL_FARMERS_PER_TRADER = sum(NUM_FARMERS_est), .groups = "drop_last") %>%
    rename(NUM_NUM_FARMERS_TRADER = NUM_NUM_FARMERS_est) %>%
    arrange(as.integer(NUM_NUM_FARMERS_TRADER)) %>%
    nest() %>%
    rename(NUM_FARMERS_TRADER_distribution = data)

  left_join(links, farmers_per_trader, by = "BUYER") %>%
    unnest(cols = c(NUM_FARMERS_distribution, NUM_FARMERS_TRADER_distribution)) %>%
    mutate(
      COOP_FARMER_PROPORTION = case_when(
        GEOCODE == "UNKNOWN" ~ 1,
        TRUE ~ NUM_FARMERS_est / TOTAL_FARMERS_PER_TRADER
      ),
      NUM_COOP_FARMER_PROPORTION = NUM_NUM_FARMERS_est) %>%
    nest(
      NUM_FARMERS_distribution = c(NUM_FARMERS_est, NUM_NUM_FARMERS_est),
      NUM_FARMERS_TRADER_distribution = c(TOTAL_FARMERS_PER_TRADER, NUM_NUM_FARMERS_TRADER),
      COOP_FARMER_PROPORTION_distribution = c(COOP_FARMER_PROPORTION, NUM_COOP_FARMER_PROPORTION)
    )
}

# ---------------------------------------------------------------------------
# Step 7: volume per link = production of n randomly drawn surveyed farms
# ---------------------------------------------------------------------------
step07_link_volumes <- function(links, farm_production) {
  sample_farms <- function(n) {
    sum(sample(farm_production$PRODUCTION_KG, size = n, replace = TRUE))
  }
  links %>%
    unnest(cols = c(NUM_FARMERS_distribution)) %>%
    rowwise() %>%
    mutate(
      EST_COCOA_VOLUME = sample_farms(NUM_FARMERS_est),
      NUM_EST_COCOA_VOLUME = NUM_NUM_FARMERS_est
    ) %>%
    nest(
      NUM_FARMERS_distribution = c(NUM_FARMERS_est, NUM_NUM_FARMERS_est),
      EST_COCOA_VOLUME_distribution = c(EST_COCOA_VOLUME, NUM_EST_COCOA_VOLUME)
    )
}

# ---------------------------------------------------------------------------
# Step 8: direct volume per exporter (capped), indirect remainder, and
#         per-link direct volume and value
# ---------------------------------------------------------------------------
step08_direct_per_exporter <- function(links, exporter_totals) {
  trader_bean_eq_vol <- exporter_totals$volume
  trader_val <- exporter_totals$value

  direct_per_trader <- links %>%
    unnest(EST_COCOA_VOLUME_distribution) %>%
    group_by(BUYER, NUM_EST_COCOA_VOLUME) %>%
    summarise(DIRECT_VOLUME_TRADER = sum(EST_COCOA_VOLUME), .groups = "drop_last") %>%
    rename(NUM_DIRECT_VOLUME_TRADER = NUM_EST_COCOA_VOLUME) %>%
    arrange(as.integer(NUM_DIRECT_VOLUME_TRADER)) %>%
    nest() %>%
    rename(DIRECT_VOLUME_TRADER_distribution = data)

  direct_per_trader <-
    full_join(direct_per_trader,
              trader_bean_eq_vol, by = c("BUYER" = "EXPORTER_GROUP_CLEAN")) %>%
    full_join(trader_val, by = c("BUYER" = "EXPORTER_GROUP_CLEAN", "YEAR")) %>%
    filter(!is.na(TRADER_BEQ_VOLUME_EXPORTED)) %>%
    unnest(DIRECT_VOLUME_TRADER_distribution) %>%
    # CAP: direct volume cannot exceed the exporter's potentially-direct exports
    mutate(
      DIRECT_VOLUME_TRADER = case_when(
        DIRECT_VOLUME_TRADER > TRADER_BEQ_VOLUME_EXPORTED_CAPPED ~ TRADER_BEQ_VOLUME_EXPORTED_CAPPED,
        TRUE ~ DIRECT_VOLUME_TRADER
      )
    ) %>%
    mutate(PROPORTION_DIRECT_TRADER = DIRECT_VOLUME_TRADER / TRADER_BEQ_VOLUME_EXPORTED,
           PROPORTION_DIRECT_POTENTIAL_DIRECT_SHIPMENTS = case_when(
             TRADER_BEQ_VOLUME_EXPORTED_CAPPED > 0 ~ DIRECT_VOLUME_TRADER / TRADER_BEQ_VOLUME_EXPORTED_CAPPED,
             TRUE ~ 0),
           NUM_PROPORTION_DIRECT_TRADER = NUM_DIRECT_VOLUME_TRADER) %>%
    # value is split in the same proportion as volume
    mutate(DIRECT_VAL_TRADER = VALUE_USD * PROPORTION_DIRECT_TRADER,
           NUM_DIRECT_VAL_TRADER = NUM_DIRECT_VOLUME_TRADER) %>%
    nest(
      DIRECT_VOLUME_TRADER_distribution = c(DIRECT_VOLUME_TRADER, NUM_DIRECT_VOLUME_TRADER),
      PROPORTION_DIRECT_TRADER_distribution = c(PROPORTION_DIRECT_TRADER,
                                                PROPORTION_DIRECT_POTENTIAL_DIRECT_SHIPMENTS,
                                                NUM_PROPORTION_DIRECT_TRADER),
      DIRECT_VAL_TRADER_distribution = c(DIRECT_VAL_TRADER, NUM_DIRECT_VAL_TRADER)
    )

  # Link back to links; UNKNOWN links receive the indirect remainder
  links <-
    full_join(links,
              direct_per_trader %>%
                select(BUYER, YEAR, DIRECT_VOLUME_TRADER_distribution,
                       DIRECT_VAL_TRADER_distribution),
              by = "BUYER") %>%
    unnest(cols = c(COOP_FARMER_PROPORTION_distribution, DIRECT_VOLUME_TRADER_distribution,
                    DIRECT_VAL_TRADER_distribution)) %>%
    left_join(trader_bean_eq_vol, by = c("BUYER" = "EXPORTER_GROUP_CLEAN", "YEAR")) %>%
    mutate(
      INDIRECT_TRADED_VOLUME = TRADER_BEQ_VOLUME_EXPORTED - DIRECT_VOLUME_TRADER,
      DIRECT_VOLUME_TRADER = case_when(
        GEOCODE == "UNKNOWN" ~ INDIRECT_TRADED_VOLUME,
        TRUE ~ DIRECT_VOLUME_TRADER
      )
    ) %>%
    select(-INDIRECT_TRADED_VOLUME, -TRADER_BEQ_VOLUME_EXPORTED) %>%
    left_join(trader_val, by = c("BUYER" = "EXPORTER_GROUP_CLEAN", "YEAR")) %>%
    mutate(
      INDIRECT_VAL = VALUE_USD - DIRECT_VAL_TRADER,
      DIRECT_VAL_TRADER = case_when(
        GEOCODE == "UNKNOWN" ~ INDIRECT_VAL,
        TRUE ~ DIRECT_VAL_TRADER
      )
    ) %>%
    select(-INDIRECT_VAL, -VALUE_USD) %>%
    mutate(COOP_DIRECT_VOLUME = COOP_FARMER_PROPORTION * DIRECT_VOLUME_TRADER,
           NUM_COOP_DIRECT_VOLUME = NUM_DIRECT_VOLUME_TRADER,
           COOP_DIRECT_VAL = COOP_FARMER_PROPORTION * DIRECT_VAL_TRADER,
           NUM_COOP_DIRECT_VAL = NUM_DIRECT_VOLUME_TRADER) %>%
    nest(
      COOP_FARMER_PROPORTION_distribution = c(COOP_FARMER_PROPORTION, NUM_COOP_FARMER_PROPORTION),
      DIRECT_VOLUME_TRADER_distribution = c(DIRECT_VOLUME_TRADER, NUM_DIRECT_VOLUME_TRADER),
      COOP_DIRECT_VOLUME_distribution = c(COOP_DIRECT_VOLUME, NUM_COOP_DIRECT_VOLUME),
      DIRECT_VAL_TRADER_distribution = c(DIRECT_VAL_TRADER, NUM_DIRECT_VAL_TRADER),
      COOP_DIRECT_VAL_distribution = c(COOP_DIRECT_VAL, NUM_COOP_DIRECT_VAL)
    )

  list(links = links, direct_per_trader = direct_per_trader)
}

# ---------------------------------------------------------------------------
# Step 9: aggregate shipments into trade flows and split each flow into a
#         direct part and an unknown/indirect part
# ---------------------------------------------------------------------------
step09_trade_flows <- function(trade, direct_per_trader) {
  # THE FINEST LEVEL OF THE OUTPUT: original exporter name x group x destination
  # x product code x year
  trade_links <- trade %>%
    group_by(EXPORTER_ORIGINAL, EXPORTER_GROUP_CLEAN, COUNTRY_OF_DESTINATION, PRODUCT_B_CODE, YEAR) %>%
    summarise(TRADE_LINK_BEQ_VOLUME = sum(BEAN_EQUIVALENT_VOLUME),
              TRADE_LINK_VAL = sum(VALUE_USD),
              TRADE_LINK_BEQ_VOLUME_POTENTIAL_DIRECT = sum(POTENTIAL_DIRECT_VOL),
              TRADE_LINK_VAL_POTENTIAL_DIRECT = sum(POTENTIAL_DIRECT_VAL),
              .groups = "drop_last")

  joined <- inner_join(direct_per_trader %>%
                         select(BUYER, YEAR, PROPORTION_DIRECT_TRADER_distribution),
                       trade_links,
                       by = c("BUYER" = "EXPORTER_GROUP_CLEAN", "YEAR")) %>%
    unnest(cols = c(PROPORTION_DIRECT_TRADER_distribution))

  renest <- function(df) {
    df %>% nest(
      PROPORTION_DIRECT_TRADER_distribution = c(PROPORTION_DIRECT_TRADER,
                                                PROPORTION_DIRECT_POTENTIAL_DIRECT_SHIPMENTS,
                                                NUM_PROPORTION_DIRECT_TRADER),
      TRADE_LINK_DIRECT_VOLUME_distribution = c(TRADE_LINK_DIRECT_VOLUME, NUM_TRADE_LINK_DIRECT_VOLUME),
      TRADE_LINK_DIRECT_VAL_distribution = c(TRADE_LINK_DIRECT_VAL, NUM_TRADE_LINK_DIRECT_VAL)
    )
  }

  # Direct part: potentially-direct volume x exporter's direct share of it
  direct <- joined %>%
    mutate(TRADE_LINK_DIRECT_VOLUME = TRADE_LINK_BEQ_VOLUME_POTENTIAL_DIRECT * PROPORTION_DIRECT_POTENTIAL_DIRECT_SHIPMENTS,
           NUM_TRADE_LINK_DIRECT_VOLUME = NUM_PROPORTION_DIRECT_TRADER,
           TRADE_LINK_DIRECT_VAL = TRADE_LINK_VAL_POTENTIAL_DIRECT * PROPORTION_DIRECT_POTENTIAL_DIRECT_SHIPMENTS,
           NUM_TRADE_LINK_DIRECT_VAL = NUM_PROPORTION_DIRECT_TRADER) %>%
    renest()

  # Remaining part (named *_DIRECT_* too, so both can be stacked later)
  unknown <- joined %>%
    mutate(TRADE_LINK_DIRECT_VOLUME = TRADE_LINK_BEQ_VOLUME_POTENTIAL_DIRECT * (1 - PROPORTION_DIRECT_POTENTIAL_DIRECT_SHIPMENTS) + (TRADE_LINK_BEQ_VOLUME - TRADE_LINK_BEQ_VOLUME_POTENTIAL_DIRECT),
           NUM_TRADE_LINK_DIRECT_VOLUME = NUM_PROPORTION_DIRECT_TRADER,
           TRADE_LINK_DIRECT_VAL = TRADE_LINK_VAL_POTENTIAL_DIRECT * (1 - PROPORTION_DIRECT_POTENTIAL_DIRECT_SHIPMENTS) + (TRADE_LINK_VAL - TRADE_LINK_VAL_POTENTIAL_DIRECT),
           NUM_TRADE_LINK_DIRECT_VAL = NUM_PROPORTION_DIRECT_TRADER) %>%
    renest()

  list(direct = direct, unknown = unknown)
}

# ---------------------------------------------------------------------------
# Step 10: allocate each flow's direct part to suppliers by farmer share
# ---------------------------------------------------------------------------
step10_allocate_to_suppliers <- function(links, trade_flows) {
  allocate <- function(link_rows, flows) {
    inner_join(link_rows %>%
                 select(GEOCODE, SUPPLIER_ID, COOPACRONYM_AANAME, COOPNAME_AADENOMINATION, FLOW_ID,
                        CERTIFICATIONS, CERTIFIED, BUYER, YEAR,
                        COOP_FARMER_PROPORTION_distribution),
               flows %>%
                 select(EXPORTER_ORIGINAL, BUYER, YEAR, COUNTRY_OF_DESTINATION, PRODUCT_B_CODE,
                        TRADE_LINK_DIRECT_VOLUME_distribution, TRADE_LINK_DIRECT_VAL_distribution),
               by = c("BUYER", "YEAR"),
               relationship = "many-to-many") %>%   # one link x many flows of its buyer
      unnest(cols = c(COOP_FARMER_PROPORTION_distribution, TRADE_LINK_DIRECT_VOLUME_distribution,
                      TRADE_LINK_DIRECT_VAL_distribution)) %>%
      mutate(COOP_SOURCED_DIRECT_VOLUME_BEQ = COOP_FARMER_PROPORTION * TRADE_LINK_DIRECT_VOLUME,
             NUM_COOP_SOURCED_DIRECT_VOLUME_BEQ = NUM_TRADE_LINK_DIRECT_VOLUME,
             COOP_SOURCED_DIRECT_VAL = COOP_FARMER_PROPORTION * TRADE_LINK_DIRECT_VAL,
             NUM_COOP_SOURCED_DIRECT_VAL = NUM_COOP_FARMER_PROPORTION) %>%
      nest(
        COOP_FARMER_PROPORTION_distribution = c(COOP_FARMER_PROPORTION, NUM_COOP_FARMER_PROPORTION),
        TRADE_LINK_DIRECT_VOLUME_distribution = c(TRADE_LINK_DIRECT_VOLUME, NUM_TRADE_LINK_DIRECT_VOLUME),
        COOP_SOURCED_DIRECT_VOLUME_BEQ_distribution =
          c(COOP_SOURCED_DIRECT_VOLUME_BEQ, NUM_COOP_SOURCED_DIRECT_VOLUME_BEQ),
        TRADE_LINK_DIRECT_VAL_distribution = c(TRADE_LINK_DIRECT_VAL, NUM_TRADE_LINK_DIRECT_VAL),
        COOP_SOURCED_DIRECT_VAL_distribution = c(COOP_SOURCED_DIRECT_VAL, NUM_COOP_SOURCED_DIRECT_VAL)
      )
  }
  bind_rows(
    allocate(links %>% filter(!GEOCODE == "UNKNOWN"), trade_flows$direct),
    allocate(links %>% filter(GEOCODE == "UNKNOWN"), trade_flows$unknown)
  )
}

# ---------------------------------------------------------------------------
# Step 11: cooperatives that export directly (all their exports are traced to
#          their own region; unions of cooperatives are split equally)
# ---------------------------------------------------------------------------
step11_exporting_coops <- function(supplier_links, suppliers, trade, exporter_totals, config) {
  n_draws <- config$n_draws
  tag <- config$exporting_cooperative_tag
  trader_bean_eq_vol <- exporter_totals$volume
  trader_val <- exporter_totals$value

  # Members of unions of cooperatives (e.g. ECOOKIM in Côte d'Ivoire)
  union_coops <-
    supplier_links %>%
    select(SUPPLIER_ID, GEOCODE, COOPACRONYM_AANAME, COOPNAME_AADENOMINATION, BUYER, FLOW_ID,
           CERTIFICATIONS, CERTIFIED) %>%
    mutate(CERTIFIED = as.character(CERTIFIED)) %>%
    filter(BUYER %in% config$cooperative_unions & !COOPACRONYM_AANAME %in% config$cooperative_unions) %>%
    distinct(COOPACRONYM_AANAME, .keep_all = TRUE)
  union_size <- table(union_coops$BUYER)

  # Exporting cooperatives found in customs data, matched to suppliers by acronym
  known_exporting_coop_acronyms <-
    trade %>% filter(grepl(tag, EXPORTER_GROUP_CLEAN, fixed = TRUE)) %>%
    pull(EXPORTER_GROUP_CLEAN) %>%
    gsub(x = ., pattern = paste0(" ", tag), replacement = "", fixed = TRUE) %>%
    unique() %>% sort()

  exporting_coops_0 <-
    suppliers %>%
    select(SUPPLIER_ID, GEOCODE, COOPACRONYM_AANAME = COOPACRONYM,
           COOPNAME_AADENOMINATION = COOPNAME, CERTIFICATIONS, CERTIFIED) %>%
    mutate(FLOW_ID = "EXPORT_COOP") %>%
    mutate(CERTIFIED = as.character(CERTIFIED)) %>%
    mutate(BUYER = case_when(
      COOPACRONYM_AANAME %in% known_exporting_coop_acronyms ~
        paste0(known_exporting_coop_acronyms[match(COOPACRONYM_AANAME, known_exporting_coop_acronyms)], " ", tag),
      TRUE ~ NA
    ))

  # Where several suppliers share an exporting cooperative's acronym, keep only
  # the one whose full name matches the analyst-chosen pattern
  # (config$exporting_cooperative_shared_acronyms: columns acronym, fullname_pattern).
  dis <- config$exporting_cooperative_shared_acronyms
  if (!is.null(dis) && nrow(dis) > 0) {
    for (i in seq_len(nrow(dis))) {
      exporting_coops_0 <- exporting_coops_0 %>%
        mutate(BUYER = case_when(
          COOPACRONYM_AANAME == dis$acronym[i] & !grepl(dis$fullname_pattern[i], COOPNAME_AADENOMINATION) ~ NA,
          TRUE ~ BUYER
        ))
    }
  }

  exporting_coops_0 <- exporting_coops_0 %>%
    filter(!is.na(BUYER)) %>%
    filter(!is.na(GEOCODE)) %>%
    distinct(COOPACRONYM_AANAME, .keep_all = TRUE)

  diagnostics <- list(
    known_exporting_coop_acronyms = known_exporting_coop_acronyms,
    # exporters that are neither tagged cooperatives nor disclosing buyers:
    # check these for cooperatives missing from exporting_cooperative_rules.csv
    potentially_new_exporting_cooperatives = trade %>%
      filter(!grepl(tag, EXPORTER_GROUP_CLEAN, fixed = TRUE) &
               !(EXPORTER_GROUP_CLEAN %in% supplier_links$BUYER)) %>%
      pull(EXPORTER_GROUP_CLEAN) %>% unique() %>% sort()
  )

  exporting_coops <- bind_rows(exporting_coops_0, union_coops) %>%
    filter(!is.na(BUYER))

  # No cooperative exports directly (possible in other countries): nothing to add
  if (nrow(exporting_coops) == 0) {
    return(list(exporting_cooperatives = tibble(BUYER = character()), flows = tibble(),
                diagnostics = diagnostics))
  }

  exporting_coops <- exporting_coops %>%
    mutate(MULTIPLE_GEOCODES_MULTIPLIER = 1) %>%
    group_by(SUPPLIER_ID, BUYER) %>%
    mutate(MULTIPLE_GEOCODES_MULTIPLIER = sum(MULTIPLE_GEOCODES_MULTIPLIER)) %>%
    mutate(COOP_FARMER_PROPORTION = case_when(
      BUYER %in% config$cooperative_unions ~ list(rep(MULTIPLE_GEOCODES_MULTIPLIER * 1/as.numeric(union_size[BUYER]), n_draws)),
      TRUE ~ list(rep(1, n_draws))
    )) %>%
    select(-MULTIPLE_GEOCODES_MULTIPLIER) %>%
    unnest(COOP_FARMER_PROPORTION) %>%
    group_by() %>%
    nest(COOP_FARMER_PROPORTION = COOP_FARMER_PROPORTION) %>%
    ungroup() %>%
    mutate(COOP_FARMER_PROPORTION_distribution = map(COOP_FARMER_PROPORTION, ~ .x %>%
                                                       mutate(NUM_COOP_FARMER_PROPORTION = row.names(.)))) %>%
    select(-COOP_FARMER_PROPORTION)

  # The cooperative's whole export volume and value is direct
  exporting_coops <-
    exporting_coops %>%
    left_join(trader_bean_eq_vol, by = c("BUYER" = "EXPORTER_GROUP_CLEAN")) %>%
    left_join(trader_val, by = c("BUYER" = "EXPORTER_GROUP_CLEAN", "YEAR")) %>%
    unnest(cols = c(COOP_FARMER_PROPORTION_distribution)) %>%
    rowwise() %>%
    mutate(COOP_DIRECT_VOLUME = COOP_FARMER_PROPORTION * TRADER_BEQ_VOLUME_EXPORTED,
           COOP_DIRECT_VAL = COOP_FARMER_PROPORTION * VALUE_USD,
           NUM_COOP_DIRECT_VOLUME = NUM_COOP_FARMER_PROPORTION,
           NUM_COOP_DIRECT_VAL = NUM_COOP_FARMER_PROPORTION,
           NUM_DIRECT_VOLUME_TRADER = NUM_COOP_FARMER_PROPORTION,
           NUM_DIRECT_VAL_TRADER = NUM_COOP_FARMER_PROPORTION) %>%
    rename(DIRECT_VOLUME_TRADER = TRADER_BEQ_VOLUME_EXPORTED,
           DIRECT_VAL_TRADER = VALUE_USD) %>%
    nest(
      COOP_FARMER_PROPORTION_distribution = c(COOP_FARMER_PROPORTION, NUM_COOP_FARMER_PROPORTION),
      COOP_DIRECT_VOLUME_distribution = c(COOP_DIRECT_VOLUME, NUM_COOP_DIRECT_VOLUME),
      COOP_DIRECT_VAL_distribution = c(COOP_DIRECT_VAL, NUM_COOP_DIRECT_VAL),
      DIRECT_VOLUME_TRADER_distribution = c(DIRECT_VOLUME_TRADER, NUM_DIRECT_VOLUME_TRADER),
      DIRECT_VAL_TRADER_distribution = c(DIRECT_VAL_TRADER, NUM_DIRECT_VAL_TRADER)
    )

  # Link to trade flows (exporting cooperative x destination x product)
  trade_links_expcoop <- trade %>%
    group_by(EXPORTER_ORIGINAL, EXPORTER_GROUP_CLEAN, COUNTRY_OF_DESTINATION, PRODUCT_B_CODE, YEAR) %>%
    summarise(TRADE_LINK_DIRECT_VOLUME = sum(BEAN_EQUIVALENT_VOLUME),
              TRADE_LINK_DIRECT_VAL = sum(VALUE_USD),
              .groups = "drop_last")

  flows <-
    inner_join(exporting_coops %>%
                 select(GEOCODE, SUPPLIER_ID, COOPACRONYM_AANAME, COOPNAME_AADENOMINATION,
                        FLOW_ID, CERTIFICATIONS,
                        BUYER, YEAR,
                        COOP_FARMER_PROPORTION_distribution),
               trade_links_expcoop %>%
                 select(EXPORTER_ORIGINAL, EXPORTER_GROUP_CLEAN, YEAR, COUNTRY_OF_DESTINATION, PRODUCT_B_CODE,
                        TRADE_LINK_DIRECT_VOLUME, TRADE_LINK_DIRECT_VAL),
               by = c("BUYER" = "EXPORTER_GROUP_CLEAN", "YEAR"),
               relationship = "many-to-many") %>%   # union members x flows of the union
    unnest(cols = c(COOP_FARMER_PROPORTION_distribution)) %>%
    mutate(COOP_SOURCED_DIRECT_VOLUME_BEQ = COOP_FARMER_PROPORTION * TRADE_LINK_DIRECT_VOLUME,
           COOP_SOURCED_DIRECT_VAL = COOP_FARMER_PROPORTION * TRADE_LINK_DIRECT_VAL,
           NUM_TRADE_LINK_DIRECT_VOLUME   = NUM_COOP_FARMER_PROPORTION,
           NUM_TRADE_LINK_DIRECT_VAL      = NUM_COOP_FARMER_PROPORTION,
           NUM_COOP_SOURCED_DIRECT_VOLUME_BEQ = NUM_COOP_FARMER_PROPORTION,
           NUM_COOP_SOURCED_DIRECT_VAL    = NUM_COOP_FARMER_PROPORTION) %>%
    nest(
      COOP_FARMER_PROPORTION_distribution = c(COOP_FARMER_PROPORTION, NUM_COOP_FARMER_PROPORTION),
      TRADE_LINK_DIRECT_VOLUME_distribution = c(TRADE_LINK_DIRECT_VOLUME, NUM_TRADE_LINK_DIRECT_VOLUME),
      TRADE_LINK_DIRECT_VAL_distribution = c(TRADE_LINK_DIRECT_VAL, NUM_TRADE_LINK_DIRECT_VAL),
      COOP_SOURCED_DIRECT_VOLUME_BEQ_distribution = c(COOP_SOURCED_DIRECT_VOLUME_BEQ, NUM_COOP_SOURCED_DIRECT_VOLUME_BEQ),
      COOP_SOURCED_DIRECT_VAL_distribution = c(COOP_SOURCED_DIRECT_VAL, NUM_COOP_SOURCED_DIRECT_VAL)
    )

  list(exporting_cooperatives = exporting_coops, flows = flows, diagnostics = diagnostics)
}

# ---------------------------------------------------------------------------
# Step 12: replace the generic flows of exporting cooperatives by their own
# ---------------------------------------------------------------------------
step12_combine <- function(links, supplier_flows, expcoop) {
  exp_buyers <- unique(expcoop$exporting_cooperatives$BUYER)
  list(
    providers = bind_rows(
      links %>%
        mutate(CERTIFIED = as.character(CERTIFIED)) %>%
        filter(!BUYER %in% exp_buyers) %>%
        select(-NUM_FARMERS, -NUM_FARMERS_TRADER_distribution),
      expcoop$exporting_cooperatives
    ),
    flows = bind_rows(
      supplier_flows %>% filter(!BUYER %in% exp_buyers),
      expcoop$flows
    )
  )
}
