# =============================================================================
# run_supply_chain_model.R: run the whole supply-chain model
# =============================================================================
#   inputs <- prepare_inputs(read_inputs(config), config)
#   result <- run_supply_chain_model(inputs, config)
#   result$output          the final table (one row per flow)
#   result$draws           every Monte Carlo draw, per flow (for uncertainty)
#   result$supplier_links  every supplier link with its draws
#   result$diagnostics     things an analyst should look at after each run
# =============================================================================

run_supply_chain_model <- function(inputs, config, verbose = TRUE) {
  say <- function(...) if (verbose) message(...)
  set.seed(config$seed)
  n_draws <- config$n_draws

  # Step 0.1 --------------------------------------------------------------
  say("Step 0.1  re-attributing shipments and flagging potentially direct ones")
  trade <- step01_attribute_shipments(inputs$trade, inputs$supplier_links, config)
  exporter_totals <- summarise_exporters(trade)
  total_volume <- sum(trade$BEAN_EQUIVALENT_VOLUME)
  total_value  <- sum(trade$VALUE_USD)
  reattributed_to <- trade %>%
    filter(!EXP_DISCL & IMP_CFI_TRADER) %>% pull(IMPORTER_GROUP_CLEAN) %>% unique() %>% sort()
  # Disclosing buyers whose name matches no exporter or importer group in the
  # customs data. Their links cannot be used, so their suppliers' volumes end
  # up as INDIRECT/UNKNOWN. Usually a spelling difference (e.g. "OFI" vs
  # "OLAM"): fix the name in the supplier links or in company_group_rules.csv.
  # (Diagnostic only: does not change the result.)
  unmatched_buyers <- setdiff(
    unique(na.omit(inputs$supplier_links$BUYER)),
    c(trade$EXPORTER_GROUP_CLEAN, trade$IMPORTER_GROUP_CLEAN, config$cooperative_unions)) %>% sort()

  # Steps 1-4 -------------------------------------------------------------
  say("Steps 1-4 building supplier links")
  disclosed <- step02_disclosed_links(inputs$supplier_links)
  licensed  <- step03_licensed_buyer_links(inputs$licensed_buyers, trade, config)
  combined  <- step04_combine_links(disclosed, licensed, trade)
  supplier_links <- combined$supplier_links   # disclosed links, renamed
  links <- combined$links

  # Steps 5-7 -------------------------------------------------------------
  say("Step 5    farmers per link (", n_draws, " draws)")
  links <- step05_farmers_per_link(links, supplier_links, n_draws)
  say("Step 6    each link's share of its buyer's farmers")
  links <- step06_link_shares(links)
  say("Step 7    volume per link from farm production survey")
  links <- step07_link_volumes(links, inputs$farm_production)

  # Step 8 ----------------------------------------------------------------
  say("Step 8    direct volume per exporter (capped)")
  s8 <- step08_direct_per_exporter(links, exporter_totals)
  links <- s8$links
  check_total(total_volume, sum_of_means(links, "COOP_DIRECT_VOLUME_distribution", "COOP_DIRECT_VOLUME"), "volume after step 8")
  check_total(total_value,  sum_of_means(links, "COOP_DIRECT_VAL_distribution", "COOP_DIRECT_VAL"), "value after step 8")

  # Step 9 ----------------------------------------------------------------
  say("Step 9    splitting trade flows into direct and remaining parts")
  trade_flows <- step09_trade_flows(trade, s8$direct_per_trader)
  both <- bind_rows(trade_flows$direct, trade_flows$unknown)
  check_total(total_volume, sum_of_means(both, "TRADE_LINK_DIRECT_VOLUME_distribution", "TRADE_LINK_DIRECT_VOLUME"), "volume after step 9")
  check_total(total_value,  sum_of_means(both, "TRADE_LINK_DIRECT_VAL_distribution", "TRADE_LINK_DIRECT_VAL"), "value after step 9")
  rm(both)

  # Step 10 ---------------------------------------------------------------
  say("Step 10   allocating direct parts to suppliers")
  supplier_flows <- step10_allocate_to_suppliers(links, trade_flows)
  check_total(total_volume, sum_of_means(supplier_flows, "COOP_SOURCED_DIRECT_VOLUME_BEQ_distribution", "COOP_SOURCED_DIRECT_VOLUME_BEQ"), "volume after step 10")
  check_total(total_value,  sum_of_means(supplier_flows, "COOP_SOURCED_DIRECT_VAL_distribution", "COOP_SOURCED_DIRECT_VAL"), "value after step 10")

  # Steps 11-12 -----------------------------------------------------------
  say("Step 11   exporting cooperatives")
  expcoop <- step11_exporting_coops(supplier_links, inputs$suppliers, trade, exporter_totals, config)
  say("Step 12   combining")
  combined <- step12_combine(links, supplier_flows, expcoop)
  check_total(total_volume, sum_of_means(combined$flows, "COOP_SOURCED_DIRECT_VOLUME_BEQ_distribution", "COOP_SOURCED_DIRECT_VOLUME_BEQ"), "volume after step 12")
  check_total(total_value,  sum_of_means(combined$flows, "COOP_SOURCED_DIRECT_VAL_distribution", "COOP_SOURCED_DIRECT_VAL"), "value after step 12")
  # every exporting cooperative must have all of its exports traced to itself
  coop_rows <- combined$providers %>% filter(grepl(config$exporting_cooperative_tag, BUYER, fixed = TRUE))
  coop_share <- if (nrow(coop_rows) == 0) numeric(0) else coop_rows %>%
    rowwise() %>%
    mutate(MEAN = mean(unlist(COOP_FARMER_PROPORTION_distribution$COOP_FARMER_PROPORTION))) %>%
    pull(MEAN)
  if (length(coop_share) > 0 && mean(coop_share, na.rm = TRUE) != 1) stop("exporting cooperative shares do not sum to 1")

  # Final -----------------------------------------------------------------
  say("Final     summarising draws and formatting output")
  fin <- finalise_output(combined$flows, trade, inputs$regions, inputs$bean_equivalence, config)
  check_total(total_volume, sum(fin$output$VOLUME_BEAN_EQUIVALENT), "final volume")
  check_total(total_value,  sum(fin$output[[config$value_column_name]]), "final value")

  list(
    output = plain_output(fin$output, config),
    draws = plain_draws(fin$flows_long),
    supplier_links = combined$providers,
    diagnostics = list(
      sourcing_summary = sourcing_summary(fin$output),
      shipments_reattributed_to_committed_importers = reattributed_to,
      exporting_cooperatives_found = expcoop$diagnostics$known_exporting_coop_acronyms,
      exporters_that_may_be_cooperatives = expcoop$diagnostics$potentially_new_exporting_cooperatives,
      disclosing_buyers_not_in_customs = unmatched_buyers
    )
  )
}

#' Write the results to output_dir.
write_model_outputs <- function(result, inputs, config, output_dir) {
  dir.create(file.path(output_dir, "intermediate"), recursive = TRUE, showWarnings = FALSE)
  out_csv <- file.path(output_dir, config$output_file)
  readr::write_csv(result$output, out_csv)
  saveRDS(result$supplier_links, file.path(output_dir, "intermediate", paste0("supplier_links_with_draws_", config$year, ".rds")))
  saveRDS(result$draws, file.path(output_dir, "intermediate", paste0("flows_with_draws_", config$year, ".rds")))
  saveRDS(inputs, file.path(output_dir, "intermediate", paste0("model_inputs_", config$year, ".rds")))
  saveRDS(result$diagnostics, file.path(output_dir, "intermediate", paste0("diagnostics_", config$year, ".rds")))
  invisible(out_csv)
}
