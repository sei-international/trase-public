# Building the supplier map

The model needs to know **which companies buy from which cooperatives**, **where each cooperative is**, and ideally **how many farmers** supply each buyer. Nobody publishes this as one table: it is assembled from company disclosures. In Côte d'Ivoire this is the largest part of the work.

The result is two tables, `supplier_links` and `suppliers`, described in [`docs/INPUT_DATA.md`](../docs/INPUT_DATA.md).

## What is in this folder

| File | Use it to |
|---|---|
| `templates/supplier_map_template.xlsx` | fill in the two tables by hand. Sheet `how_to_fill_in` explains every column. The template `read_inputs.R` reads it directly. |
| `templates/supplier_map_example.xlsx` | see a filled-in example (fictional data) |
| `supplier_map_tools.py` | reusable Python steps: name cleaning, fuzzy matching, locating suppliers, farmer numbers, building links, checking the tables |
| `build_supplier_map_cote_divoire_2024.py` | see the complete Côte d'Ivoire 2024 workflow in one script, as a worked example |

**By hand or by script?** With a few dozen disclosures, the spreadsheet is quickest. With many disclosures in different formats, or to repeat the work every year, write a script; `build_supplier_map_cote_divoire_2024.py` shows how, and `supplier_map_tools.py` has the parts that apply anywhere.

Before running the model, check the tables:

```python
import sys; sys.path.insert(0, "supplier_map")
import pandas as pd, geopandas as gpd
import supplier_map_tools as smt
links = pd.read_excel("my_supplier_map.xlsx", sheet_name="supplier_links")
suppliers = pd.read_excel("my_supplier_map.xlsx", sheet_name="suppliers")
region_codes = gpd.read_file("my_regions.geojson")["REGION_CODE"]
smt.check_model_tables(links, suppliers, region_codes)   # prints any problems
```

## The steps

| Step | What happens | Function in `supplier_map_tools.py` | In the Côte d'Ivoire script |
|---|---|---|---|
| 1. Collect | Download each company's supplier disclosure: PDF tables (extracted with Tabula), Excel files, online maps, reports | – | step 1 |
| 2. Standardise | Reshape every disclosure to the same columns: company, trader, supplier short name, full name, type, coordinates, area name, farmer numbers, certification | – | steps 1–2 |
| 3. Clean names | Upper case, remove accents, unify spellings (e.g. "STE COOP" → "COOPERATIVE"), separate short names from full names | `normalise_text`, `remove_ignore_phrases` | step 3 |
| 4. Match to known suppliers | Fuzzy-match names to last year's map, so one cooperative keeps one identity | `build_fuzzy_map` | step 3 |
| 5. Locate | Assign each cooperative to a region, in order: hand fixes → place name → last year's location → coordinates (point in polygon) | `locate_suppliers` | step 3 |
| 6. Traders vs others | Decide which disclosing companies are **traders** (exporters); the others are information sources only (see below) | – | step 3 ("TRADER NAME FIXES") |
| 7. Fill gaps | Fill missing attributes (location) from a reference table such as last year's map | `fill_from_reference` | step 4 |
| 8. Farmer numbers | Fill missing farmer numbers per link: the same buyer's number for the cooperative in another year, otherwise the mean of other buyers' numbers for the cooperative | `impute_farmer_numbers` | step 4 ("Farmer numbers") |
| 9. Build links | One row per supplier × buyer; choose the buyer; combine certifications; number the links | `make_links` | step 4 |
| 10. Write and check | Write the two tables in the standard format and check them | `check_model_tables` | step 5 |

Company names in the links do not need to match the customs spelling exactly: the model applies the country's company-name rules to `BUYER`, and splits combined buyers ("A + B") into one link per company (`standardise_buyer_names()` in `model/R/prepare_inputs.R`). Still, write one company per link where you can.

## The Côte d'Ivoire script

`build_supplier_map_cote_divoire_2024.py` runs the five steps in order. Each step writes its result to `<data folder>/supplier_map/work/`, so you can stop, check a file by hand, and carry on:

```bash
python3 supplier_map/build_supplier_map_cote_divoire_2024.py --data-dir <folder>
python3 supplier_map/build_supplier_map_cote_divoire_2024.py --data-dir <folder> --from-step 4
```

It needs the companies' disclosures in `<folder>/supplier_map/company_disclosures_2024/` and last year's map in `<folder>/supplier_map/last_year/`. Without `--data-dir` it uses the fake ones in `data/synthetic_raw_inputs/` (see `data/README.md`). Their file names start with `SYNTHETIC_`; the script reads a file under its original name if it exists, and otherwise the `SYNTHETIC_` copy, so you can run it straight away and look at the files each step writes in `data/synthetic_raw_inputs/supplier_map/work/`:

```bash
python3 supplier_map/build_supplier_map_cote_divoire_2024.py
``` Many lines are corrections for specific companies or cooperatives in the 2024 disclosures: they show the kind of decisions you will need to make, but do not apply elsewhere. The final step writes `supplier_map/supplier_links_2024.csv` and `supplier_map/suppliers_2024.csv`, in the same format as the spreadsheet template.

For Côte d'Ivoire, the supplier map builds on the public dataset **Ivorian Cocoa Cooperatives and their Buyers (IC2B)**: Guye, V. (2024), https://doi.org/10.14428/DVN/YBWJOR, licensed CC BY 4.0. Its documentation describes how records referring to the same cooperative are recognised.

## Decisions to make and write down

- **Who is a trader** (`BUYER_IS_TRADER`). A company that discloses suppliers counts as a trader only if it exports from the country and its exports in customs data are consistent with what it says it sources.
  - In Côte d'Ivoire, chocolate makers, retailers, the union ECOOKIM and Rainforest Alliance are kept as **information sources**: their links stay in the map, with `BUYER_IS_TRADER = FALSE`.
  - The companies treated this way are Albert Heijn, Alfred Ritter, Alter Eco, Blommer, Colruyt, Ecookim, Ferrero, Hershey, Mars, Mondelēz, Nestlé, Puratos, Tony's Chocolonely and Valrhona.
  - To check a candidate, compare the company's volumes in customs data (as exporter or importer) with its reported sourcing.
- **Disclosures about someone else's suppliers.** A manufacturer may disclose which trader supplies it from which cooperatives: Tony's Chocolonely → Cocoasource; Alfred Ritter → Kruger and Suscom. These links are given to the trader (`BUYER` = the trader, `DISCLOSED_BY` = the manufacturer).
- **The buyer of a link** is the trader named in the disclosure if there is one, otherwise the disclosing company, except certification schemes, which never buy.
- **Farmer numbers.** Use the buyer's figure for that cooperative where disclosed. Otherwise use other buyers' figures for the same cooperative, or leave it empty: the model then draws from all known sizes.
- **Company names** must give the same group name as the customs data once the country's `company_group_rules.csv` is applied. If a company appears under a new name (e.g. "OFI" for Olam), add the name to its rule.

## Things to watch

- `remove_ignore_phrases` removes the listed words even inside other words. For example, "DE" is removed from "DEDOUGOU". Check fuzzy matches by hand: `build_fuzzy_map` prints each one.
- Matching cooperatives to last year's map by **short name** is quick but risky: short names can be shared by different cooperatives, so check duplicates.

Python packages: see `requirements.txt` in the toolkit's top folder.
