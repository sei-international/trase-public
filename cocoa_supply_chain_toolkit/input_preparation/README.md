# Preparing the other model inputs

These scripts build the Côte d'Ivoire customs, farm-production and licensed-buyer inputs from raw data. They run on the fake raw files in `data/synthetic_raw_inputs/` (see `data/README.md`) and write their results there:

```bash
Rscript input_preparation/trade/clean_customs_cote_divoire_2024.R
Rscript input_preparation/licensed_buyers/locate_licensed_buyers_cote_divoire.R
Rscript -e 'rmarkdown::render("input_preparation/farm_production/farm_production_from_kit_survey.Rmd", knit_root_dir = getwd())'
```

Run them from the toolkit's top folder. Each one sources `input_preparation/setup.R`, which loads the toolkit and sets `input_path()` to `MODEL_DATA_DIR` (default `data/synthetic_raw_inputs/`). To run them on real files, set `MODEL_DATA_DIR` to a folder with the same layout. They were written to be run line by line in RStudio, so they print many intermediate tables; with the small synthetic files, some of these are empty.

| Folder | Script | Produces | Notes for another country |
|---|---|---|---|
| `trade/` (customs records) | `clean_customs_cote_divoire_2024.R` | `customs/cocoa_exports_2024.csv` | Steps that carry over: rename columns, translate country names (`helpers/cote_divoire_helpers.R`), derive HS6 and tonnes, convert currency, flag price and weight outliers per HS code, compare with UN Comtrade. Manual fixes by shipment ID only apply to that file. Needs the `countrycode` package. |
| `farm_production/` | `farm_production_from_kit_survey.Rmd` | `farm_survey/kit_farm_production.csv` | Keeps the Côte d'Ivoire farms of the KIT survey (country code 2) and their total annual production. A new country needs its own survey. The KIT data also cover Ghana. |
| `licensed_buyers/` | `locate_licensed_buyers_cote_divoire.R` | `licensed_buyers/licensed_buyers_2021.csv` | Matches the department names in the regulator's lists to department codes, with hand fixes for spelling. Optional: in the Côte d'Ivoire data no licensed buyer matches an exporter, so this step adds nothing there. |

The supplier map has its own folder: `supplier_map/`.
