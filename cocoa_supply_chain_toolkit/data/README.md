# Example data

`synthetic_cote_divoire/` holds **made-up** inputs with the same files, columns and formats as the real Côte d'Ivoire inputs. The companies, cooperatives, shipments, farmer numbers and production figures are fictional, and model results from them mean nothing. The data exist so every script can run and you can inspect each step.

The one real file is `regions/departments.geojson`: the public department boundaries of Côte d'Ivoire, derived from GADM.

`make_synthetic_data.py` regenerates the folder (Python standard library only, fixed random seed):

```bash
python3 data/make_synthetic_data.py
```

To use real data, put the files in another folder with the same layout and set `MODEL_DATA_DIR` to it. File names and columns are listed in `countries/cote_divoire/read_inputs.R` and `docs/INPUT_DATA.md`. Real customs data are usually licensed: check before sharing.

| Folder | What it holds |
|---|---|
| `supplier_map/` | the two supplier tables, in the standard format (the same columns as the spreadsheet template) |
| `customs/` | customs export records |
| `farm_survey/` | farm production survey (in the format of the KIT survey) |
| `licensed_buyers/` | licensed buyers and their department |
| `regions/` | department boundaries (real, public) |
| `deforestation_metrics/` | cocoa deforestation, emissions, production and cocoa area per department, region attributes and company commitments, in the formats the deforestation step reads; not real Earth Engine results |
| `quality_check_data/` | extra datasets used only by the Côte d'Ivoire quality-check report |

## Raw inputs for the worked examples

`synthetic_raw_inputs/` holds **made-up raw files** for the examples that start from raw data. Regenerate it with:

```bash
python3 data/make_synthetic_raw_inputs.py     # needs pandas, geopandas, openpyxl and Rscript
```

| Folder | Fake version of | Used by |
|---|---|---|
| `supplier_map/company_disclosures_2024/` | companies' supplier disclosures, each in the layout of the real file (scraped web maps, tables extracted from PDFs, spreadsheets) | `supplier_map/build_supplier_map_cote_divoire_2024.py`, step 1 |
| `supplier_map/work/step1_by_company/2024_ritter_sport.csv` | a list typed in by hand | the same, step 1 |
| `supplier_map/last_year/` | last year's supplier map and disclosures | steps 2–4 |
| `customs/raw/`, `customs/ISO2_ENGLISH_COUNTRY_NAMES.csv` | the raw customs extract and a country-code list | `input_preparation/trade/` |
| `farm_survey/0 Cocoa_Livelihoods_export_Dataverse.RData` | the KIT survey file (download the real one from https://doi.org/10.7910/DVN/82TWZJ) | `input_preparation/farm_production/` |
| `licensed_buyers/` | the regulator's yearly lists of licensed buyers | `input_preparation/licensed_buyers/` |
| `earth_engine_exports/` | the CSVs that `cocoa_deforestation_metrics.js` exports to Google Drive | `deforestation_metrics/reshape_earth_engine_exports.py` |
| `regions/` | a copy of the real department boundaries | all of the above |

The company names in the fake disclosures are there only because the example script reads each company's file by name. **Their contents are invented**: they are not what those companies published.

The examples write their results into this folder too, next to their inputs. Running `make_synthetic_raw_inputs.py` again resets it.
