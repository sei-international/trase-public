# =============================================================================
# <COUNTRY> cocoa <YEAR>: model settings          (TEMPLATE: copy this folder)
# =============================================================================
#   1. Copy countries/_template/ to countries/<your_country>/ (e.g. cameroon)
#   2. Fill in every item marked TODO below, and the rule tables in rules/
#   3. Write read_inputs.R (see the template next to this file)
#   4. Run:  Rscript run_model.R <your_country>
# docs/NEW_COUNTRY_GUIDE.md explains each choice; the Côte d'Ivoire
# folder (countries/cote_divoire/) is a complete worked example.
# =============================================================================

country_dir <- file.path(TOOLKIT_ROOT, "countries", "_template")   # TODO: your folder name

read_list <- function(file, column) {
  path <- file.path(country_dir, "rules", file)
  readr::read_delim(path, delim = ";", show_col_types = FALSE)[[column]]
}

config <- list(

  # --- Basics ----------------------------------------------------------------
  country_name = "TODO COUNTRY NAME",     # as written in COUNTRY_OF_ORIGIN, upper case
  year = 2024,                            # TODO: model year
  n_draws = as.integer(Sys.getenv("MODEL_N_DRAWS", "1000")),
  seed = 5,
  data_dir = Sys.getenv("MODEL_DATA_DIR", "TODO/path/to/your/data"),
  output_file = "supply_chains_TODO_2024.csv",
  value_column_name = "FOB_USD",          # TODO: CIF_USD or FOB_USD, whichever customs report

  # --- Deforestation exposure (model/R/deforestation_exposure.R) ---------------------------
  # Last export year your cocoa map can represent (the year of its imagery,
  # plus the lag you use). Later model years print a warning.
  cocoa_map_valid_until = 2021,   # TODO

  # --- Commodity (cocoa; usually no change needed) ----------------------------
  commodity = list(
    name = "COCOA",
    hs_chapter_prefix = "180",
    excluded_hs6 = "180200",
    product_names_by_hs4 = c("1801" = "COCOA BEANS", "1802" = "COCOA WASTE",
                             "1803" = "COCOA PASTE", "1804" = "COCOA BUTTER",
                             "1805" = "COCOA POWDER"),
    bean_equivalence_file = file.path(TOOLKIT_ROOT, "commodities", "cocoa", "bean_conversion_factors.csv")
  ),

  # --- IDs (TODO: choose a 2-letter prefix, e.g. CM for Cameroon) -------------
  ids = list(
    cooperative_prefix = "XX-COOPERATIVE-", cooperative_width = 4,
    licensed_buyer_prefix = "XX-LICENSED-BUYER-", licensed_buyer_width = 3,
    unknown_supplier_id = "XX-SUPPLIER-UNKNOWN",
    unknown_region_id = "XX-UNKNOWN",     # exporter disclosed nothing
    indirect_region_id = "XX-INDIRECT"   # exporter disclosed, but not this volume
  ),

  # Turns a region code from your input files into the ID used in the output.
  # Called one value at a time; must turn "UNKNOWN" into unknown_region_id.
  # TODO: the simplest choice is to keep your codes as they are:
  region_to_id = function(code) if (identical(code, "UNKNOWN")) "XX-UNKNOWN" else code,

  # --- Company names ----------------------------------------------------------
  rules = list(
    company_groups  = read_name_rules(file.path(country_dir, "rules", "company_group_rules.csv")),
    exporting_cooperatives = read_name_rules(file.path(country_dir, "rules", "exporting_cooperative_rules.csv"))
  ),
  exporting_cooperative_tag = "(COOPERATIVE)",

  # Unions of cooperatives exporting for their members (none: character(0))
  cooperative_unions = character(0),

  # Signatories of a sector commitment (in Côte d'Ivoire: the Cocoa & Forests
  # Initiative; check which commitments apply in your country) whose purchases
  # from non-disclosing exporters are counted under them. Empty file = off.
  commitment_signatories = read_list("commitment_signatories.csv", "company_group"),

  # Licensed buyers whose name differs from their exporter group (none: character(0))
  licensed_buyer_to_exporter = character(0),

  # Exporting cooperatives whose acronym is shared by several suppliers
  exporting_cooperative_shared_acronyms = readr::read_delim(
    file.path(country_dir, "rules", "exporting_cooperative_shared_acronyms.csv"),
    delim = ";", show_col_types = FALSE)
)
