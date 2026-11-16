# Cocoa supply chains and deforestation: toolkit

This toolkit links a country's cocoa exports to the sub-national regions and cooperatives they were sourced from, and measures the deforestation linked to cocoa in each region. It follows the method [Trase](https://trase.earth) developed for Côte d'Ivoire, and is set up so it can be applied to another country (for example Cameroon or Nigeria).

It has three parts:

```
                       ┌───────────────────────────────┐
 customs export        │ 1. SUPPLY-CHAIN MODEL (R)     │   who exported how much,
 records ─────────────►│    model/ + countries/<x>/    │──►from which region and
 supplier map ────────►│                               │   cooperative, to where
 farm survey ─────────►└───────────────────────────────┘
                                                              ┌────────────────────┐
                       ┌───────────────────────────────┐      │ combined: cocoa    │
 forest-change maps ──►│ 2. DEFORESTATION METRICS      │──────│ deforestation per  │
 cocoa map ───────────►│    (Earth Engine + Python)    │      │ exporter, importer │
 carbon map ──────────►│    deforestation_metrics/     │      └────────────────────┘
                       └───────────────────────────────┘
                       ┌───────────────────────────────┐
 company disclosures ─►│ 3. SUPPLIER MAP               │──► input to part 1
 (PDF, Excel, maps)    │    supplier_map/ (spreadsheet │
                       │    template or Python)        │
                       └───────────────────────────────┘
```

## Start here

| If you want to… | Read |
|---|---|
| look up a term | [`docs/GLOSSARY.md`](docs/GLOSSARY.md) |
| understand what the model does, step by step | [`docs/HOW_THE_MODEL_WORKS.md`](docs/HOW_THE_MODEL_WORKS.md) |
| see exactly which data the model needs, and what it produces | [`docs/INPUT_DATA.md`](docs/INPUT_DATA.md) |
| set the model up for a new country | [`docs/NEW_COUNTRY_GUIDE.md`](docs/NEW_COUNTRY_GUIDE.md) |
| compute cocoa deforestation per region | [`docs/DEFORESTATION_METRICS.md`](docs/DEFORESTATION_METRICS.md) |
| build the supplier map | [`supplier_map/README.md`](supplier_map/README.md) |

## Quick start (Côte d'Ivoire example, synthetic data)

You need R (4.2 or later) and Python (3.10 or later). From this folder:

```bash
Rscript install_packages.R                      # once
python3 -m pip install -r requirements.txt      # once
Rscript run_model.R                             # writes output/cote_divoire/
MODEL_N_DRAWS=50 Rscript run_model.R            # quicker, 50 Monte Carlo draws
Rscript results_by_exporter_and_destination.R   # summary tables
```

`run_model.R` writes two tables: the supply chains (`supply_chains_cote_divoire_2024.csv`) and the same rows with their cocoa deforestation and degradation, emissions and cocoa land (`..._with_deforestation.csv`). `results_by_exporter_and_destination.R` sums them per exporter, importing country and region.

> **All example data are made up.** They have the real file structure, but the cooperatives, shipments and numbers are fictional, so results from them mean nothing. The one real file is the department boundary file, which comes from geoBoundaries under a CC BY 3.0 IGO licence (see `data/synthetic_cote_divoire/regions/SOURCE.md`).

## What you can run

Everything below runs with what is in this folder, from the toolkit's top folder. The examples that start from raw data use the synthetic raw files in `data/synthetic_raw_inputs/` (made by `python3 data/make_synthetic_raw_inputs.py`) and write their results there, so the model's ready-made inputs in `data/synthetic_cote_divoire/` are not touched.

| Example | Command | Reads | Writes |
|---|---|---|---|
| The model, with deforestation | `Rscript run_model.R` | `data/synthetic_cote_divoire/` | `output/cote_divoire/` |
| Summary tables | `Rscript results_by_exporter_and_destination.R` | `output/cote_divoire/` | `output/cote_divoire/summaries/` |
| Quality-check report | `Rscript -e 'rmarkdown::render("countries/cote_divoire/reports/quality_checks_2024.Rmd", knit_root_dir = getwd())'` | `output/cote_divoire/`, `data/synthetic_cote_divoire/quality_check_data/` | an HTML report next to the .Rmd |
| Supplier map from company disclosures | `python3 supplier_map/build_supplier_map_cote_divoire_2024.py` | `data/synthetic_raw_inputs/supplier_map/` (fake disclosures in each company's format, and last year's map) | `data/synthetic_raw_inputs/supplier_map/` |
| Supplier map by hand | open `supplier_map/templates/supplier_map_template.xlsx` | – | – |
| Customs cleaning | `Rscript input_preparation/trade/clean_customs_cote_divoire_2024.R` | `data/synthetic_raw_inputs/customs/raw/` | `data/synthetic_raw_inputs/customs/` |
| Farm production from a survey | `Rscript -e 'rmarkdown::render("input_preparation/farm_production/farm_production_from_kit_survey.Rmd", knit_root_dir = getwd())'` | `data/synthetic_raw_inputs/farm_survey/` | `data/synthetic_raw_inputs/farm_survey/` |
| Licensed buyers located | `Rscript input_preparation/licensed_buyers/locate_licensed_buyers_cote_divoire.R` | `data/synthetic_raw_inputs/licensed_buyers/` | the same folder |
| Regions ready for Earth Engine | `python3 deforestation_metrics/prepare_regions_for_earth_engine.py data/synthetic_cote_divoire/regions/departments.geojson regions.zip` | the boundary file | `regions.zip` |
| Earth Engine exports reshaped | see `docs/DEFORESTATION_METRICS.md`, step 4 | `data/synthetic_raw_inputs/earth_engine_exports/` | `data/synthetic_raw_inputs/deforestation_metrics/` |
| Earth Engine script | paste `deforestation_metrics/cocoa_deforestation_metrics.js` into the Code Editor | your uploaded regions | CSVs in your Google Drive |

`sh tests/test_examples.sh` runs all of these (except Earth Engine itself) in a temporary copy of the folder.

The Côte d'Ivoire scripts were written for the real data, which is larger and messier than the synthetic files; with the synthetic files, some of their checks print empty tables or warnings. Their results from the synthetic files are not meaningful.

## Folder layout

```
run_model.R                 runs the model (and the deforestation step) for one country:
                            Rscript run_model.R <country>
results_by_exporter_and_destination.R   summary tables from a run
install_packages.R, requirements.txt    R and Python packages

model/                      THE MODEL: the same for every country
  load.R                      loads packages and everything in R/
  R/prepare_inputs.R          input tables -> model inputs (IDs, name cleaning, bean equivalents)
  R/company_names.R           company-name cleaning driven by rule tables
  R/model_steps.R             the model, one function per step (matches docs/HOW_THE_MODEL_WORKS.md)
  R/summarise_results.R       averages the Monte Carlo draws and formats the result table
  R/run_supply_chain_model.R  runs all steps with consistency checks
  R/deforestation_exposure.R  links cocoa deforestation to the supply chains

countries/
  cote_divoire/               complete worked example
    config.R                    every country-specific setting, explained
    read_inputs.R               the only file that knows the input file names
    rules/                      company-name rules, commitment signatories, manual fixes (CSV)
    reports/quality_checks_2024.Rmd   quality checks and charts on the results (example)
  _template/                  copy this to start a new country

commodities/cocoa/          bean-conversion factors (ICCO)

deforestation_metrics/
  cocoa_deforestation_metrics.js     Earth Engine script, set up per country
  prepare_regions_for_earth_engine.py  region boundaries -> zipped shapefile to upload
  reshape_earth_engine_exports.py    Earth Engine CSVs -> tables per region and year

supplier_map/
  templates/                  blank spreadsheet for the supplier map, and a filled-in example
  supplier_map_tools.py       reusable steps for building the supplier map
  build_supplier_map_cote_divoire_2024.py   the Côte d'Ivoire workflow in one script

input_preparation/          building the other inputs from raw data (Côte d'Ivoire examples)
  trade/                      cleaning customs records
  farm_production/            farm production from the KIT survey
  licensed_buyers/            locating licensed buyers

data/
  synthetic_cote_divoire/     ready-made model inputs (synthetic)
  synthetic_raw_inputs/       raw files for the input-preparation and supplier-map examples (synthetic)
  make_synthetic_data.py, make_synthetic_raw_inputs.py   the scripts that make them
tests/                      automated checks (run after any code change)
docs/                       documentation
```

## Tests

`sh tests/run_all_tests.sh` checks that:

1. **The model gives the expected results** on the example data and on test data that triggers every special case (unions of cooperatives, shared cooperative short names, licensed buyers, commitment signatories). If you change the model on purpose, check the new results and save them with `Rscript tests/test_model_results.R --update`.
2. **The country template runs** for a country with none of those special cases, with the supplier map in the spreadsheet format.
3. **Company names in the supplier map** are cleaned like customs names, combined buyers are split, and duplicates merged.
4. **Each deforestation step** gives what `docs/HOW_THE_MODEL_WORKS.md` describes.
5. **The Earth Engine post-processing** puts each band in the right metric, year and region, and sums regions correctly.
6. **The farmer-number estimates** follow each rule in `docs/HOW_THE_MODEL_WORKS.md` (Step 5).
7. **The supplier-map tools and spreadsheet templates** match the format the model expects.
8. **The whole example runs** from input files to summary tables.
9. **Every worked example runs** on the synthetic raw inputs (`tests/test_examples.sh`).

## Published method and data

- Trase (2026). *SEI-PCS Côte d'Ivoire cocoa v1.2 supply chain map: Data sources and methods.* https://doi.org/10.48650/3KGC-VB46
- French, N., Guye, V., Gollnow, F., Biddle, H., Ribeiro, V., Meyfroidt, P., Renier, C. & zu Ermgassen, E. K. H. J. (2026). *Côte d'Ivoire cocoa supply chain v1.2 (2022–2024)* [Data set]. Trase. https://doi.org/10.48650/f7bx-1a03
- Guye, V. (2024). *Ivorian Cocoa Cooperatives and their Buyers (IC2B), database v1.0.* https://doi.org/10.14428/DVN/YBWJOR
- Renier, C. et al. (2023). Transparency, traceability and deforestation in the Ivorian cocoa supply chain. *Environmental Research Letters* 18, 024030. https://doi.org/10.1088/1748-9326/acad8e
- Trase (2022). *Commodity deforestation exposure and carbon emissions assessment.* https://doi.org/10.48650/GE7V-Q043
- Godar, J. et al. (2015). Towards more accurate and policy relevant footprint analyses. *Ecological Economics* 112, 25–35.

## Credits

Trase's Côte d'Ivoire cocoa model is a collaboration between the Stockholm Environment Institute and UCLouvain. The authors include Valentin Guye, Niamh French, Florian Gollnow, Erasmus zu Ermgassen, Vivian Ribeiro and Cécile Renier. The deforestation metrics are by Florian Gollnow, Carina Mueller and Niamh French.
