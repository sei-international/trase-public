# Input data and results

The model needs **six tables**. A country's `read_inputs()` (`countries/<country>/read_inputs.R`) reads them from whatever files you have and returns them with **exactly these column names**. `prepare_inputs()` checks that the columns are there and stops with a clear message if one is missing. The deforestation step needs up to four more tables (section 7).

Example files for every table are in `data/synthetic_cote_divoire/` (made up), and `countries/cote_divoire/read_inputs.R` shows how they are read. Words in *italics* are explained in [`GLOSSARY.md`](GLOSSARY.md).

## 1. `supplier_links`: who says they buy from whom

One row per *link*: a **supplier** (usually a cooperative; also a warehouse or another first buyer) and **one company that says it buys from it**. A cooperative sold to by three companies has three rows. Suppliers that no company names still get a row, with `BUYER` empty, so they stay on the map.

The easiest way to build this table is the spreadsheet template `supplier_map/templates/supplier_map_template.xlsx` (sheet `supplier_links`); `supplier_map_example.xlsx` is a filled-in example. `supplier_map/README.md` explains how to collect the information.

| Column | Type | Required | Meaning |
|---|---|---|---|
| `SUPPLIER_NUMBER` | whole number | yes | Identifies the supplier. The same number as in `suppliers`. |
| `YEAR` | whole number | yes | Model year. Rows from other years are ignored. |
| `REGION_CODE` | text | yes | Region the supplier is in, as in `regions`. Links without a region are not used. |
| `SUPPLIER_SHORT_NAME` | text | yes | Short name or acronym. Used to recognise *exporting cooperatives*. |
| `SUPPLIER_NAME` | text | yes | Full name |
| `BUYER` | text | no | Company that says it buys from this supplier: the trader named in the disclosure if there is one, otherwise the company that published it. The model cleans it with the same *company-name rules* as the customs names, so any spelling the rules recognise works. Several companies can be written `A + B`: the link is then split into one per company. Empty for suppliers no company names. |
| `BUYER_IS_TRADER` | TRUE/FALSE | yes | TRUE if the buyer is an *exporter* whose exports are in the customs data. FALSE for chocolate makers, retailers and certification schemes, and when `BUYER` is empty. |
| `NUMBER_OF_FARMERS` | number | no | Farmers in this supplier who sell to this buyer, as disclosed or estimated (`impute_farmer_numbers()` in `supplier_map/supplier_map_tools.py`). Leave empty if unknown: the model then draws a value from the known ones. |
| `CERTIFICATIONS` | text | no | Certification schemes mentioned |
| `CERTIFIED` | TRUE/FALSE | no | Whether any certification is mentioned |
| `LINK_ID` | text | yes | Unique for each row, e.g. `2024-1` |
| `DISCLOSED_BY` | text | yes | Whose publication the row comes from |

**Why `BUYER_IS_TRADER` matters.**
- Only links whose buyer is a trader count as that trader's direct sourcing. Companies that publish supplier lists but are not exporters (chocolate makers, retailers, certification schemes), or whose exports in customs data are far below what they say they source, should be FALSE. Write down your list and the reason for each company.
- The pool of farmer numbers that unknown links are drawn from uses only trader links. Chocolate makers often report more farmers than the trader they buy through.
- A shipment from an exporter that published nothing is counted under its foreign buyer when that buyer is a trader here (*importer re-attribution*, see `HOW_THE_MODEL_WORKS.md`, Step 0.1).

## 2. `suppliers`: one row per supplier

| Column | Type | Required | Meaning |
|---|---|---|---|
| `SUPPLIER_NUMBER` | whole number | yes | One row per supplier |
| `YEAR`, `REGION_CODE`, `SUPPLIER_SHORT_NAME`, `SUPPLIER_NAME`, `CERTIFICATIONS`, `CERTIFIED` | | | as in `supplier_links` |

Used to locate cooperatives that export directly (Step 11). Template sheet: `suppliers`.

## 3. `licensed_buyers`: registered intermediaries with a known location (optional)

Licensed buyers such as the *acheteurs agréés* registered with Côte d'Ivoire's Conseil du Café-Cacao. If your country has no such register, return an empty table with these columns (the template does).

| Column | Type | Meaning |
|---|---|---|
| `SHORT_NAME` | text | Short name or representative |
| `COMPANY_NAME` | text | Company name. Matched to exporter names in customs data. |
| `REGION_CODE` | text | Region where it operates |

## 4. `trade`: customs export records

One row per export shipment, or the most detailed level available.

| Column | Type | Meaning |
|---|---|---|
| `YEAR` | whole number | Model year |
| `COUNTRY_OF_ORIGIN` | text | The producing country |
| `COUNTRY_OF_DESTINATION` | text | Importing country, upper case |
| `EXPORTER` | text | Exporter name exactly as in customs |
| `IMPORTER` | text | Foreign buyer name as in customs. Leave empty if not reported; the importer re-attribution then does nothing. |
| `HS6` | text | 6-digit HS product code, for example `180100` (cocoa beans) |
| `HS_CODE` | text | Most detailed product code available (national 8–10 digits, or the HS6) |
| `NET_WEIGHT_KG` | number | Net weight, kg |
| `VALUE_USD` | number | Value in USD. The output column is named by `value_column_name` in `config.R` (`CIF_USD` or `FOB_USD`). |

Every `HS6` must appear in `commodities/cocoa/bean_conversion_factors.csv` (the *bean-equivalent* factors). Codes in `commodity$excluded_hs6` (cocoa shells, 180200) are dropped.

## 5. `farm_production`: farm production survey

| Column | Type | Meaning |
|---|---|---|
| `FARM_PRODUCTION_KG` | number | Total cocoa produced by one surveyed farm in a year, kg |

A representative sample of the country's cocoa farms. The model samples from it with replacement. Without a survey, see `NEW_COUNTRY_GUIDE.md`, "If data are missing".

## 6. `regions`: the sub-national units

| Column | Type | Meaning |
|---|---|---|
| `REGION_CODE` | text | Code used in `REGION_CODE` above |
| `REGION_NAME` | text | Name written in the output |

**Use the same regions everywhere.** The same boundaries and codes must be used in the supplier map, the licensed buyers and Earth Engine, so that sourcing and deforestation can be joined. `config$region_to_id()` turns a `REGION_CODE` into the `REGION_ID` written in the output; the deforestation tables use `REGION_ID`.

## 7. Deforestation inputs (optional)

Read by `read_spatial_inputs()` in `countries/<country>/read_inputs.R`. If a country has no such function, `run_model.R` skips the deforestation step. `REGION_ID` must equal `REGION_ID` in the model output. The model year must be present in the first two tables.

| Table | Columns |
|---|---|
| Cocoa deforestation per region and year (written by `deforestation_metrics/reshape_earth_engine_exports.py`) | `REGION_ID`, `YEAR`, `COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL`, `COCOA_DEFORESTATION_AND_DEGRADATION_ANNUAL` (ha), `COCOA_GROSS_EMISSIONS_15_YEARS_TOTAL`, `COCOA_GROSS_EMISSIONS_ANNUAL`, `COCOA_NET_EMISSIONS_15_YEARS_TOTAL`, `COCOA_NET_EMISSIONS_ANNUAL` (t CO2) |
| Cocoa production per region and year | `REGION_ID`, `YEAR`, `COCOA_TONNES` |
| Cocoa area per region | `REGION_ID`, `COCOA_HA` |
| Region attributes (optional) | `REGION_ID` plus any columns, e.g. `ECOREGION` |
| Company commitments (optional) | `EXPORTER_GROUP` (as in the output), `HAS_COMMITMENT` (TRUE/FALSE), `COMMITMENT_TYPE`, `START_YEAR`, `END_YEAR` (empty if still in force) |

## Settings and rule tables (`countries/<country>/`)

| File | What it holds |
|---|---|
| `config.R` | Every setting, each explained in the file: year, data folder, IDs, value column, unions of cooperatives, and so on |
| `rules/company_group_rules.csv` | `order;pattern;value;comment`: company-name spelling (a regular expression) → company group. Applied to customs names and to the buyers in the supplier map. The first matching rule wins. |
| `rules/exporting_cooperative_rules.csv` | Same format: customs name → `<ACRONYM> (COOPERATIVE)` for cooperatives that export directly. The acronym must equal the supplier's `SUPPLIER_SHORT_NAME`. |
| `rules/exporting_cooperative_shared_acronyms.csv` | `acronym;fullname_pattern;comment`: when several suppliers share an exporting cooperative's acronym, keep only the one whose full name matches the pattern |
| `rules/commitment_signatories.csv` | One company group per row: signatories of a sector commitment (in Côte d'Ivoire, the Cocoa & Forests Initiative) |

**Regular expressions in one paragraph.** A pattern matches any name that *contains* it. `|` means "or": `CARGIL|CARGRILL` matches "CARGILL WEST AFRICA" and "CARGRILL SA". `^` means "starts with" and `$` "ends with": `^OFI$` matches only "OFI". Names are upper-cased and accents removed before matching. Test a pattern in R with `grepl("CARGIL|CARGRILL", "CARGILL WEST AFRICA")`.

## Results (`output/<country>/`)

| File | Contents |
|---|---|
| `supply_chains_<country>_<year>.csv` | One row per *flow*: exporter (customs name) × destination × product × supplier and region, with mean volume and value |
| `supply_chains_<country>_<year>_with_deforestation.csv` | The same rows plus deforestation, emissions and cocoa land (only when deforestation inputs exist) |
| `intermediate/flows_with_draws_<year>.rds` | The same flows with every *Monte Carlo draw*, for uncertainty ranges |
| `intermediate/supplier_links_with_draws_<year>.rds` | Every supplier link with its draws (farmer share, volumes), for checking |
| `intermediate/model_inputs_<year>.rds` | The prepared inputs |
| `intermediate/diagnostics_<year>.rds` | Direct/indirect/unknown shares, re-attributed shipments, names to check |
| `intermediate/deforestation_per_tonne_<year>.rds` | Untraced-production weights and per-tonne figures used for the deforestation columns |

### Columns of the supply-chain table

| Column | Meaning |
|---|---|
| `COUNTRY_OF_ORIGIN`, `COUNTRY_OF_DESTINATION` | Producing and importing country |
| `EXPORTER` | Exporter name as in customs |
| `EXPORTER_NAME_CLEANED` | Cleaned exporter name |
| `EXPORTER_GROUP` | Company group (after importer re-attribution) |
| `YEAR` | Model year |
| `HS6`, `HS_CODE` | 6-digit and detailed product codes |
| `PRODUCT_WEIGHT_KG` | Product weight, kg |
| `BEAN_EQUIVALENT_KG` | Cocoa *bean-equivalent* weight, kg |
| `CIF_USD` / `FOB_USD` | Value, USD (name set by `value_column_name`) |
| `SOURCING_TYPE` | `DIRECT`, `INDIRECT` or `UNKNOWN` (see glossary) |
| `REGION_ID`, `REGION_NAME` | Region the cocoa came from; for indirect and unknown sourcing, the IDs set in `config$ids` and the names INDIRECT SOURCING / UNKNOWN |
| `PRODUCT`, `COMMODITY` | Product name (e.g. COCOA BUTTER) and commodity |
| `SUPPLIER_ID`, `SUPPLIER_SHORT_NAME`, `SUPPLIER_NAME` | Supplier (cooperative or licensed buyer), or the unknown-supplier ID |

### Extra columns in the table with deforestation

| Column | Meaning |
|---|---|
| `DEFORESTATION_AND_DEGRADATION_HA_15Y` | Cocoa deforestation and degradation linked to the flow, ha, over the 15-year *allocation period* |
| `DEFORESTATION_AND_DEGRADATION_HA_ANNUAL` | Same, one year (with the 4-year *lag*) |
| `GROSS_EMISSIONS_TCO2_15Y`, `GROSS_EMISSIONS_TCO2_ANNUAL` | t CO2 from deforestation (not degradation) |
| `NET_EMISSIONS_TCO2_15Y`, `NET_EMISSIONS_TCO2_ANNUAL` | Same, minus carbon stored in cocoa (84.41 t CO2/ha), floored at 0 |
| `COCOA_LAND_HA` | Cocoa land needed to grow the flow's volume, ha |
| e.g. `ECOREGION` | From the optional region attributes; UNKNOWN for indirect and unknown sourcing |
| `ZERO_DEFORESTATION_COMMITMENT` | From the optional company commitments: the commitment type if one was in force in the model year, NONE, or UNKNOWN if the exporter is not listed |

`HOW_THE_MODEL_WORKS.md` ("Using the results") shows how to sum these by exporter or destination.
