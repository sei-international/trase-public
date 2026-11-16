# =============================================================================
# Côte d'Ivoire cocoa 2024: model settings
# =============================================================================
# Everything that is specific to one country (or one year) lives in this file
# and in the rule tables in rules/. The model code in model/ is generic.
# To set up a new country, copy countries/_template/ and fill it in; see
# docs/NEW_COUNTRY_GUIDE.md.
# =============================================================================

country_dir <- file.path(TOOLKIT_ROOT, "countries", "cote_divoire")

config <- list(

  # --- Basics ----------------------------------------------------------------
  country_name = "COTE D'IVOIRE",          # written in COUNTRY_OF_ORIGIN
  year = 2024,
  n_draws = as.integer(Sys.getenv("MODEL_N_DRAWS", "1000")),  # Monte Carlo draws
  seed = 5,                                # random seed (results are reproducible)

  # Folder with the input files read by read_inputs.R. Defaults to the
  # synthetic example data. Point it at the real data with
  #   Sys.setenv(MODEL_DATA_DIR = "/path/to/data")
  data_dir = Sys.getenv("MODEL_DATA_DIR",
                        file.path(TOOLKIT_ROOT, "data", "synthetic_cote_divoire")),
  output_file = "supply_chains_cote_divoire_2024.csv",

  # Customs value field. 2024 customs data report CIF; other years used FOB.
  value_column_name = "CIF_USD",

  # --- Deforestation exposure (model/R/deforestation_exposure.R) ---------------------------
  # Last export year the cocoa map can represent. The ETH cocoa map shows
  # cocoa around 2019-2021, so cocoa planted later is missed. Runs for later
  # years still work but print a warning. See docs/DEFORESTATION_METRICS.md.
  cocoa_map_valid_until = 2021,

  # --- Commodity ---------------------------------------------------------------
  commodity = list(
    name = "COCOA",
    hs_chapter_prefix = "180",               # HS codes of the commodity start with this
    excluded_hs6 = "180200",                 # cocoa shells and waste: not modelled
    product_names_by_hs4 = c("1801" = "COCOA BEANS", "1802" = "COCOA WASTE",
                             "1803" = "COCOA PASTE", "1804" = "COCOA BUTTER",
                             "1805" = "COCOA POWDER"),
    bean_equivalence_file = file.path(TOOLKIT_ROOT, "commodities", "cocoa", "bean_conversion_factors.csv")
  ),

  # --- IDs -------------------------------------------------------------------
  ids = list(
    cooperative_prefix = "CI-COOPERATIVE-", cooperative_width = 4,
    licensed_buyer_prefix = "CI-LICENSED-BUYER-", licensed_buyer_width = 3,
    unknown_supplier_id = "CI-SUPPLIER-UNKNOWN",
    unknown_region_id = "CI-UNKNOWN",        # exporter disclosed nothing
    indirect_region_id = "CI-INDIRECT"        # exporter disclosed, but not this volume
  ),

  # Converts a department code as used in the input files ("CI-3.1.2_1")
  # into the region ID used in the output ("CI-030102"). Called one value at a time.
  region_to_id = function(series) {
    code <- series
    code <- gsub("\\.", "0", code)
    code <- gsub("CI-", "", code)
    code <- gsub("_1", "", code)
    if (nchar(code) == 5) {
      code <- paste0("CI-0", code)
    } else if (nchar(code) == 6) {
      code <- paste0("CI-", code)
    }
    gsub("UNKNOWN", "CI-UNKNOWN", code)
  },

  # --- Company names ----------------------------------------------------------
  rules = list(
    company_groups  = read_name_rules(file.path(country_dir, "rules", "company_group_rules.csv")),
    exporting_cooperatives = read_name_rules(file.path(country_dir, "rules", "exporting_cooperative_rules.csv"))
  ),
  # Exporting cooperatives are renamed "<ACRONYM> (COOPERATIVE)" by the rules
  # above; this is the tag the model looks for.
  exporting_cooperative_tag = "(COOPERATIVE)",

  # Unions of cooperatives that export on behalf of their members. Their
  # exports are split equally across member cooperatives (members are the
  # suppliers linked to the union as BUYER in the supplier links).
  cooperative_unions = "ECOOKIM",

  # Signatories of a sector commitment (here: Cocoa & Forests Initiative).
  # Shipments from a non-disclosing exporter TO one of these importers are
  # counted under the importer, if it also exports from the country.
  commitment_signatories = readr::read_delim(file.path(country_dir, "rules", "commitment_signatories.csv"),
                                             delim = ";", show_col_types = FALSE)$company_group,

  # Licensed buyers whose company name differs from their exporter group name
  # in customs data (licensed buyer name -> exporter group).
  licensed_buyer_to_exporter = c("BIOPARTENAIRE" = "BARRY CALLEBAUT",
                                 "CAP" = "CAP",
                                 "CYRIAN COTE D'IVOIRE" = "CYRIAN INTERNATIONAL"),

  # Exporting cooperatives whose acronym is shared by several suppliers: keep
  # only the supplier whose full name matches the pattern (checked by hand).
  exporting_cooperative_shared_acronyms = readr::read_delim(
    file.path(country_dir, "rules", "exporting_cooperative_shared_acronyms.csv"),
    delim = ";", show_col_types = FALSE)
)
