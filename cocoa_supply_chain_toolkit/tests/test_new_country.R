# =============================================================================
# test_new_country.R: does the TEMPLATE work for a country with none of the
# Côte d'Ivoire special cases (no licensed buyers, no unions of cooperatives,
# no exporting cooperatives, no commitment signatories)?
# =============================================================================
# Builds a fictional country "Testland" from the synthetic example data,
# copies countries/_template/, fills in the minimum, and runs the model.
# Run from the toolkit's top folder:  Rscript tests/test_new_country.R
# =============================================================================
TOOLKIT_ROOT <- normalizePath(getwd())
source(file.path(TOOLKIT_ROOT, "model", "load.R"))

work <- file.path(tempdir(), "testland"); unlink(work, recursive = TRUE)
dir.create(file.path(work, "data"), recursive = TRUE)
src <- file.path(TOOLKIT_ROOT, "data", "synthetic_cote_divoire")

# --- fictional input files, in the template's expected format ---------------
# (the supplier map as a spreadsheet with the two sheets of the template)
links <- read_csv(file.path(src, "supplier_map", "supplier_links_2024.csv"), show_col_types = FALSE) %>%
  filter(SUPPLIER_SHORT_NAME != "CABF")
sups <- read_csv(file.path(src, "supplier_map", "suppliers_2024.csv"), show_col_types = FALSE) %>%
  filter(SUPPLIER_SHORT_NAME != "CABF")
trade <- read_delim(file.path(src, "customs", "cocoa_exports_2024.csv"), delim = ";",
                    col_types = cols(HS6 = "c", HS_CODE = "c")) %>%
  filter(!grepl("C A B F", EXPORTER)) %>%
  transmute(YEAR, COUNTRY_OF_ORIGIN = "TESTLAND", COUNTRY_OF_DESTINATION, EXPORTER, IMPORTER = BUYER,
            HS6, HS_CODE, NET_WEIGHT_KG = NET_WEIGHT_TON * 1000, VALUE_USD = CIF_USD)
farms <- read_delim(file.path(src, "farm_survey", "kit_farm_production.csv"), delim = ";") %>%
  transmute(FARM_PRODUCTION_KG = cocoa_prod_total_kgs)
regions <- sf::read_sf(file.path(src, "regions", "departments.geojson")) %>%
  transmute(REGION_CODE = LVL_4_CODE, REGION_NAME = LVL_4_NAME)

writexl::write_xlsx(list(supplier_links = links, suppliers = sups), file.path(work, "data", "TODO_supplier_map.xlsx"))
write_csv(trade, file.path(work, "data", "TODO_customs_exports.csv"))
write_csv(farms, file.path(work, "data", "TODO_farm_production.csv"))
sf::write_sf(regions, file.path(work, "data", "TODO_regions.geojson"))

# --- country folder from the template ------------------------------------------
Sys.setenv(MODEL_DATA_DIR = file.path(work, "data"), MODEL_N_DRAWS = "50")
source(file.path(TOOLKIT_ROOT, "countries", "_template", "config.R"))
source(file.path(TOOLKIT_ROOT, "countries", "_template", "read_inputs.R"))
config$country_name <- "TESTLAND"

inputs <- prepare_inputs(read_inputs(config), config)
result <- run_supply_chain_model(inputs, config, verbose = FALSE)

o <- result$output
ok <- c(
  "model runs and produces rows" = nrow(o) > 0,
  "volume adds up to customs total" = isTRUE(all.equal(sum(o$BEAN_EQUIVALENT_KG),
                                                       sum(inputs$trade$BEAN_EQUIVALENT_VOLUME))),
  "value column named as configured" = "FOB_USD" %in% names(o),
  "some volume traced to regions" = any(o$SOURCING_TYPE == "DIRECT")
)
for (n in names(ok)) message(if (ok[[n]]) "PASS  " else "FAIL  ", n)
print(result$diagnostics$sourcing_summary)
if (!all(ok)) quit(status = 1)
