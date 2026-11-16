# Applying the method to a new country

This guide is for applying the method to another cocoa-producing country, for example Cameroon or Nigeria. The model code (`model/`) does not change. You:

1. collect data,
2. put it in the standard format (`INPUT_DATA.md`),
3. fill in one settings file and a few rule tables,
4. run, check, and refine.

The Côte d'Ivoire folder (`countries/cote_divoire/`) is a complete worked example. Terms are explained in [`GLOSSARY.md`](GLOSSARY.md).

## 0. Set up your computer

You need R (4.2 or later) and Python (3.10 or later).

```bash
Rscript install_packages.R                   # R packages
python3 -m pip install -r requirements.txt   # Python packages
Rscript run_model.R                          # run the example, from the toolkit's top folder
sh tests/run_all_tests.sh                    # optional: check everything works
```

Before starting on your own country, run the worked examples on the synthetic data (the table "What you can run" in the README lists them, with the command for each). Each example shows the files a step reads and writes.

All commands are run from the toolkit's top folder (the one containing `run_model.R`). If `sf` fails to install, install the GDAL, GEOS and PROJ libraries first (https://r-spatial.github.io/sf/#installing). For the deforestation maps you also need a Google Earth Engine account (https://earthengine.google.com).

## 1. First, check the data exist

Check each item before investing in the rest. If supplier disclosures or customs records with company names are missing, the supply-chain part cannot be done; the deforestation part can still be done at regional level.

| Need | Where to look | Used for |
|---|---|---|
| **Customs export records** with exporter names (ideally importer names too), product code, weight and value, for the year | National customs administration; commercial trade-data providers; the export regulator | Total exports per trader: the frame everything is allocated to |
| **Supplier disclosures**: which cooperatives each trader or chocolate maker buys from, ideally with farmer numbers and coordinates | Company sustainability reports and supplier lists, online supplier maps, certification registers | Direct sourcing (the traced share) |
| **Supplier locations**: coordinates, or a place name you can match to a region | The disclosures themselves; national cooperative registers; earlier mapping projects | Assigning suppliers to regions |
| **Farm production survey**: annual cocoa production per farm for a representative sample | National or research farm surveys | Turning farmer numbers into volumes |
| **Regions**: boundaries and codes of the sub-national units | National statistics office; GADM (https://gadm.org) | Everything spatial |
| **Licensed buyers or intermediaries register** (optional) | Cocoa regulator | Extra direct links |
| **Cocoa map**: where cocoa is grown, ~10 m resolution | See `DEFORESTATION_METRICS.md` | Cocoa deforestation, cocoa area, production per region |
| **Regional production** | Official statistics, or national total × cocoa area × suitability (Earth Engine section C) | Deforestation per tonne; where untraced cocoa comes from |

### If data are missing

- **No supplier disclosures.** The model still runs, but every flow is UNKNOWN. You can still report deforestation per region and the national average per tonne.
- **No cooperatives (e.g. cocoa bought by licensed buying agents or middlemen).** The model works with any first buyer that has a known location. Enter each agent or buying station as a supplier (one row in `suppliers`, with its region) and link it to the exporters it sells to, with the number of farmers it buys from if known. If only a register of licensed agents and their areas exists, use the `licensed_buyers` table: agents whose company name matches an exporter become that exporter's suppliers.
- **No farm production survey.** Build `farm_production` from what you have and record it as a major assumption. For example, simulate farms from published farm-size and yield distributions (farm size × yield, a few hundred rows), or use a survey from a neighbouring country with similar farming. Avoid a single average value: the model samples farms to represent variation between them.
- **No farmer numbers in disclosures.** Leave `NUMBER_OF_FARMERS` empty; the model draws sizes from the links that have them. If no link has a number, fill in an estimate (e.g. members per cooperative from a register) and record it.
- **No importer names in customs.** Leave `IMPORTER` empty. Importer re-attribution then does nothing.
- **No cocoa map.** See `DEFORESTATION_METRICS.md`, "Choosing a cocoa map". Without one, territorial (whole-region) deforestation can still be computed, but not deforestation linked to cocoa.
- **No regional production statistics.** Use Earth Engine section C (national production allocated by cocoa area and suitability).

## 2. Build the inputs

Work through these in order. Each produces one of the tables in [`INPUT_DATA.md`](INPUT_DATA.md).

1. **Regions.** Choose the administrative level and keep its codes everywhere. The same boundaries go into the supplier map, the model and Earth Engine.
2. **Customs records.** Clean them into the `trade` table. `input_preparation/trade/clean_customs_cote_divoire_2024.R` is the Côte d'Ivoire example: it translates country names, converts currency, derives HS6 codes and tonnes, and checks prices and weights for outliers. Compare annual totals per HS code with UN Comtrade; for Côte d'Ivoire they differ by 0–5%.
3. **Supplier map.** Collect the disclosures and build the two supplier tables. The quickest way is the spreadsheet template `supplier_map/templates/supplier_map_template.xlsx` (see `supplier_map_example.xlsx` for a filled-in example). For many disclosures, script it as in `supplier_map/build_supplier_map_cote_divoire_2024.py`. See [`supplier_map/README.md`](../supplier_map/README.md).
4. **Farm production.** Build `farm_production` from a farm survey. `input_preparation/farm_production/` shows how the KIT data were prepared for Côte d'Ivoire.
5. **Licensed buyers** (optional). See `input_preparation/licensed_buyers/`.

## 3. Set up the country folder

```bash
cp -r countries/_template countries/cameroon
```

Then edit three things:

- **`read_inputs.R`.** Point it at your files (replace each `TODO_...` file name) and rename columns if needed. This is the only file that knows your file names. If you used the spreadsheet template, the supplier map needs no renaming.
- **`config.R`.** Every item is explained in the file. The decisions that matter most:

| Setting | Decide |
|---|---|
| `country_name`, `year`, `data_dir`, `output_file` | Basics |
| `value_column_name` | Whether customs report CIF or FOB |
| `ids` | A 2-letter prefix for your IDs (e.g. `CM-`) |
| `region_to_id` | How your region codes appear in the results; keeping them unchanged is fine |
| `commodity` | HS codes and product names (the cocoa defaults usually fit) |
| `cooperative_unions` | Are there unions or networks of cooperatives that export for their members (like ECOOKIM)? |
| `commitment_signatories` (`rules/commitment_signatories.csv`) | Is there a sector commitment, like the Cocoa & Forests Initiative, whose signatories should count as disclosing traders? |
| `licensed_buyer_to_exporter` | Only if licensed-buyer names differ from exporter names |
| `cocoa_map_valid_until` | Last export year your cocoa map can represent |

- **`rules/`.** Fill these in iteratively (step 4). They use regular expressions; `INPUT_DATA.md` explains the little you need.
  - `company_group_rules.csv`: company-name spelling → company group. Start with the largest exporters. One line per group, with all spellings, for example `CARGIL|CARGRILL`. Rules are tried in order, so put specific patterns before general ones (in Côte d'Ivoire, `AGROFORCE COM` comes before `ECOM`). The same rules clean the buyers in your supplier map, so add the names used in disclosures too (e.g. `OFI` for Olam).
  - `exporting_cooperative_rules.csv`: customs names of cooperatives that export directly → `<SHORT NAME> (COOPERATIVE)`. The short name must equal the cooperative's `SUPPLIER_SHORT_NAME` in your supplier map.
  - `exporting_cooperative_shared_acronyms.csv`: only if an exporting cooperative's short name is shared by several suppliers.

## 4. Run, check, refine

```bash
MODEL_N_DRAWS=50 Rscript run_model.R cameroon      # fast, for iterating
Rscript run_model.R cameroon                       # final run, 1000 draws
Rscript results_by_exporter_and_destination.R cameroon
```

`run_model.R` prints what to check after each run:

- **Share of exports by sourcing type** (direct / indirect / unknown). For comparison, Côte d'Ivoire 2024 has about half its exports direct.
- **Exporters that may be cooperatives**: exporters that are neither known exporting cooperatives nor disclosing companies. Look for cooperatives missing from `exporting_cooperative_rules.csv`, and for spellings of disclosing traders that `company_group_rules.csv` misses.
- **Companies that disclose suppliers but match no exporter or importer in customs.** Their links are not used. Usually a spelling difference: add the spelling to `company_group_rules.csv`.

Then look at:

- **Direct volume vs total exports per trader** (`summaries/by_exporter.csv`). A trader with a direct share of 100% has more disclosed farmers than its exports can explain (the *cap*). Check its disclosures, and whether it is really a trader.
- **Direct volume vs production per region** (`summaries/by_region.csv` against your production figures). Traced volume above production suggests mislocated cooperatives or oversized links.

`countries/cote_divoire/reports/quality_checks_2024.Rmd` is a full set of checks and charts for Côte d'Ivoire. Use it as a template for your own report.

## 5. Deforestation

Follow [`DEFORESTATION_METRICS.md`](DEFORESTATION_METRICS.md): choose and validate a cocoa map, run the Earth Engine script with your `CONFIG`, reshape the exports, then point `read_spatial_inputs()` in your `read_inputs.R` at the files (the template has a skeleton). `run_model.R` then adds cocoa deforestation and degradation, emissions and cocoa land to every flow. Optionally, add region attributes (e.g. ecoregions) and companies' zero-deforestation commitments (`INPUT_DATA.md`, section 7).

## Lessons from Côte d'Ivoire

- **Name harmonisation is the bulk of the work.** Cooperatives appear under different acronyms, spellings and coordinates in different disclosures. The Côte d'Ivoire map builds on a dedicated harmonisation (IC2B, Guye 2024) to recognise when records refer to the same cooperative.
- **Not every disclosing company is a trader.** Chocolate makers, retailers and certification schemes disclose cooperatives, but their exports are tiny compared with what they source. Keep their links (they help locate cooperatives) with `BUYER_IS_TRADER = FALSE`. Write down your list and the reason for each company.
- **Disclosures by manufacturers can reveal a trader's suppliers.** In Côte d'Ivoire, Tony's Chocolonely disclosed Cocoasource's cooperatives, and Alfred Ritter disclosed Kruger's and Suscom's. These links are given to the trader.
- **Use the same company names on both sides.** When a company renames itself (Olam's cocoa business became "ofi"), add the new name to its rule.
- **Better locating raises the direct share without any change in the supply chain.** Report method changes alongside results.
- **Farmer numbers are often missing.** Record how you fill them, e.g. from earlier years or from other buyers of the same cooperative (`impute_farmer_numbers()`).

## Before you publish

- Run `sh tests/run_all_tests.sh` after any change to the code in `model/`. It confirms the example results are unchanged, unless you meant to change them (then see `tests/test_model_results.R`).
- Document the year and source of every input, and every manual rule, in the `comment` column of the rule tables.
- State the main assumptions: links represent all direct sourcing; suppliers source from their own region; the farm survey is representative; the cocoa map and its date; the allocation period and lag. Deforestation exposure is an association between trade and deforestation in the sourcing region, not attribution of responsibility.
