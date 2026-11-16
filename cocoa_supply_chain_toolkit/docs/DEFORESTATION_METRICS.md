# Deforestation metrics: cocoa deforestation and emissions per region

The supply-chain model says how much cocoa each exporter sourced from each region. The deforestation metrics say how much forest was lost to cocoa in each region. Together, they show the deforestation linked to each exporter and importing country.

The metrics are computed in Google Earth Engine (GEE) with `deforestation_metrics/cocoa_deforestation_metrics.js`. The CSVs it exports are then reshaped with `deforestation_metrics/reshape_earth_engine_exports.py`.

## Data used

| Layer | Earth Engine asset | Notes |
|---|---|---|
| Forest change | JRC Tropical Moist Forest (TMF), Vancutsem et al. 2021: `projects/JRC/TMF/<version>/AnnualChanges`, `DeforestationYear`, `DegradationYear` | Pan-tropical. AnnualChanges gives each pixel's class every December: 1 undisturbed forest, 2 degraded, 3 deforested, 4 regrowth, 5 water, 6 other. Use the latest version. |
| Cocoa map | Côte d'Ivoire and Ghana: ETH Zurich map, Kalischek et al. 2023, `projects/ee-nk-cocoa/assets/cocoa_map_threshold_065` | **Covers only Côte d'Ivoire and Ghana.** See "Choosing a cocoa map" below. |
| Carbon | WCMC above- and below-ground biomass carbon density, Soto-Navarro et al. 2020: `WCMC/biomass_carbon_density/v1_0` | Global, 300 m |
| Carbon in cocoa | 84.41 t CO2/ha = (19 + 4) t C/ha × 3.67, from Vervuurt et al. 2022 | Cocoa trees plus shade trees. Used for net emissions. |
| Regions | your own upload | Must be the same regions and codes as in the supply-chain model |

## Definitions

This toolkit uses **cocoa deforestation and degradation**: undisturbed tropical moist forest that was lost, whether to deforestation or to degradation, where the cocoa map now shows cocoa.

**Cocoa deforestation and degradation, allocation period** (`cd_15yr_tmf_loss_<Y>` → `COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL`). For export year *Y*, these are the pixels that:

- were undisturbed forest in December of *Y* − lag − ap, and
- were no longer undisturbed in December of *Y* − lag, and
- are cocoa on the cocoa map.

With the defaults (ap = 15, lag = 4), this is forest lost between *Y*−19 and *Y*−4. The **lag** reflects the years between clearing and the first harvest. The **allocation period** spreads past clearing over the cocoa produced later.

"Loss" includes **both deforestation and degradation**. Both are counted because, in cocoa areas, shade trees make many conversions show up in TMF as degradation rather than deforestation. The bands `..._tmf_def_...` (deforestation only) and `..._tmf_deg_...` (degradation only) are also computed, if you want to report them separately. Name the metric "cocoa deforestation and degradation" when reporting results.

**Cocoa deforestation and degradation, annual** (`cd_1yr_tmf_loss_<Y>` → `COCOA_DEFORESTATION_AND_DEGRADATION_ANNUAL`). This is the same calculation with ap = 1 and lag = `annual_lag` (4): forest lost during year *Y*−4 that is now cocoa, assigned to cocoa exported in year *Y*. For example, forest lost in 2017 is assigned to cocoa exported in 2021.

**Which export years are meaningful.** New cocoa trees take about four years to form a canopy visible from space, and the ETH map shows plantations in 2019–2021. So the map cannot show cocoa planted on land cleared after 2017, which means **cocoa deforestation and degradation is published only up to export year 2021**. The script computes later years (`cocoa_end`), but they miss recent expansion and should not be reported as complete.

**Cocoa emissions** (`COCOA_GROSS_/NET_EMISSIONS_ANNUAL/_15_YEARS_TOTAL`), in t CO2:

- gross = area *deforested* (not degraded) under cocoa × carbon density × 3.67
- net = gross − carbon stored in cocoa (84.41 t CO2/ha), floored at 0 and computed only where gross > 1

Emissions count **deforestation only**, unlike the area metric above, because there is no good estimate of the carbon lost to degradation yet.

**Territorial metrics** (whole region, any land use):

- `TERRITORIAL_DEFORESTATION`, `TERRITORIAL_DEGRADATION`: area deforested or degraded in year *Y*, from TMF DeforestationYear and DegradationYear
- `TERRITORIAL_UNDISTURBED_FOREST`: area of undisturbed forest in December of *Y*
- `CO2_GROSS_EMISSIONS_TERRITORIAL_DEFORESTATION`: territorial deforestation × carbon density × 3.67

**Areas** are pixel area in hectares, summed per region in the national projected coordinate system (`projection`).

**Optional sections.**

- **Section B: cocoa area.** Hectares of the cocoa map per region. The same area is used for every year the map represents.
- **Section C: cocoa production.** National production (ICCO statistics, by season: "2020" = 2019/20) is allocated to regions in proportion to "suitable cocoa": cocoa area weighted by cocoa suitability. Trase uses the suitability map of Schroth et al. (2016) for West Africa. Only the national total changes between years.
- **Cocoa yield** per region is production ÷ area.

Regional production is needed for deforestation exposure (below). If the country has official regional production statistics, they can be used instead.

## Running it

You need a Google Earth Engine account (free for research and non-commercial use: https://earthengine.google.com/signup) and the Code Editor (https://code.earthengine.google.com).

1. **Prepare your regions.** Earth Engine takes boundaries as a zipped shapefile. Convert your region file with:
   ```bash
   python3 deforestation_metrics/prepare_regions_for_earth_engine.py <your regions file> regions.zip
   ```
   (Try it on the example: `data/synthetic_cote_divoire/regions/departments.geojson`.) The file must have one feature per region and a column with the same region code as the supply-chain model (`LVL_4_CODE` for Côte d'Ivoire). Column names are cut to 10 characters, so keep them short.
2. **Upload them.** In the Code Editor, open the **Assets** tab (top left) → **NEW** → **Shape files**, choose `regions.zip`, give the asset a name (e.g. `regions_cameroon`), and click **Upload**. The upload appears in the **Tasks** tab; when it has finished, the asset is listed under Assets with a path such as `projects/<your-project>/assets/regions_cameroon`.
3. **Settings.** Paste `cocoa_deforestation_metrics.js` into a new script and fill in `CONFIG` at the top:
   - `country_code`: a short code used in the export file names (e.g. `cm`)
   - `country`: the country outline (`USDOS/LSIB_SIMPLE/2017` filtered on your country's name, as in the example)
   - `regions`: `ee.FeatureCollection('<the asset path from step 2>')`
   - `projection`: your country's projected coordinate system
   - `tmf_version`: the latest JRC TMF release in the Earth Engine catalog
   - `cocoa_map`: a binary cocoa image (see "Choosing a cocoa map" below)
   - the years (`terr_start`, `terr_end`, `cocoa_start`, `cocoa_end`) and the Google Drive folder for the exports (`export_folder`)

   **Check that you can read every asset** before running: paste, for example, `print(ee.Image('projects/ee-nk-cocoa/assets/cocoa_map_threshold_065'))` into the Code Editor and click **Run**. An error saying the asset does not exist or you have no access means you need another map, or to ask its owners for access.
4. **Run.** Click **Run**, then start each export in the **Tasks** tab (click **RUN** next to each). Each export is a CSV in your Google Drive: one row per region, one column per band. Large countries can take an hour or more.
5. **Reshape.** Download the CSVs into one folder and run:
   ```bash
   python3 deforestation_metrics/reshape_earth_engine_exports.py --country ci --input-dir <folder> --output-dir <out> \
       --cocoa-area-file <folder>/cocoa_area_ci_v1.csv --cocoa-production-file <folder>/cocoa_production_ci_v1.csv
   ```
   To try it, `data/synthetic_raw_inputs/earth_engine_exports/` holds fake exports for Côte d'Ivoire:
   ```bash
   python3 deforestation_metrics/reshape_earth_engine_exports.py --country ci \
       --input-dir data/synthetic_raw_inputs/earth_engine_exports \
       --output-dir data/synthetic_raw_inputs/deforestation_metrics \
       --cocoa-area-file data/synthetic_raw_inputs/earth_engine_exports/cocoa_area_ci_v1.csv \
       --cocoa-production-file data/synthetic_raw_inputs/earth_engine_exports/cocoa_production_ci_v1.csv
   ```
   For a new country, first add an entry to `COUNTRIES` in that script, next to the Côte d'Ivoire and Ghana ones. For example, for regions coded `CM-01.02` in a column `REGION_CO`:
   ```python
   "cm": dict(
       national_id="CM",
       region_column="REGION_CO",          # the column holding the region code
       to_region_id=lambda code: code,     # codes are already the model's REGION_ID
       drop_columns=["system:index", "REGION_CO", "NAME", ".geo"],   # everything except the bands
       aggregate_prefix_lengths=[5],       # "CM-01" = the higher administrative level
   ),
   ```
   The Earth Engine script names its exports `<name>_<country_code>.csv`; use the same code (`cm`) for `--country`.

6. **What you get.** The script writes three tables: `cocoa_deforestation_by_region.csv` (cocoa deforestation and degradation, and emissions), `territorial_emissions_by_region.csv` and `territorial_deforestation_by_region.csv`. Each has one row per region and year, plus sums for higher levels and the country. Add `--cocoa-area-file` and `--cocoa-production-file` (the section B and C exports) to also write `cocoa_area_by_region.csv` and `cocoa_production_by_region.csv`.
7. **Into the model.** Put `cocoa_deforestation_by_region.csv`, `cocoa_area_by_region.csv` and `cocoa_production_by_region.csv` in your data folder and point `read_spatial_inputs()` (in `countries/<country>/read_inputs.R`) at them. If you have official regional production or area figures instead, write them in the same two-column format.

## Choosing a cocoa map for Cameroon or Nigeria

The ETH map was trained and validated for Côte d'Ivoire and Ghana only (Kalischek et al. 2023, *Nature Food*), so it cannot be used for another country. Options to evaluate:

- **Forest Data Partnership cocoa probability models.** The Earth Engine data catalog lists these, for example "Cocoa Probability model 2025a / 2025b / 2026a". Check that they cover your country, check the exact asset ID in the catalog, and choose a probability threshold. Trase used 0.65 for the ETH map, chosen on validation data. Trase has compared ETH with a Forest Data Partnership map at a 0.5 threshold.
- **A national map** from a government or research project, if one exists and is validated.
- Newer initiatives: national land-cover and cocoa mapping (BNETD in Côte d'Ivoire), the Forest Data Partnership, commercial providers (e.g. Satelligence), and maps built on Sentinel-1/2 radar and optical data or on Google's AlphaEarth satellite embeddings. They often lack public access or consistency over time.

Whatever you use, `CONFIG.cocoa_map` must be a binary image (1 = cocoa). For example: `ee.Image(probability_map).gte(threshold)`.

Two points to report alongside the results:

- **The cocoa map is a single snapshot used for every year.** Deforestation that happened before plantations visible on the map were planted can be counted, but cocoa planted after the map date is missed.
- **Validate the map in your country.** Ground-truth points, or comparison with official cocoa area statistics, will show how reliable it is there.

## Before you rely on the numbers

1. **Run on one region first.** Set `CONFIG.regions` to a single region, run, and check the exported areas: cocoa area against the cocoa map (or official statistics), and undisturbed forest against TMF figures for that region.
2. **Projection.** Areas are computed in `CONFIG.projection`. Use a national projected or equal-area system (Côte d'Ivoire: EPSG:2041).
3. **Scale.** `export_scale` (10 m) should match the resolution of the cocoa map. A coarser scale is faster but less precise.
4. **Lag.** Both cocoa metrics use the 4-year lag (`lag`, `annual_lag`). Change both if cocoa takes a different time to become visible in your country.

## From metrics to supply chains

`model/R/deforestation_exposure.R` links the deforestation per region to the supply chains: deforestation per tonne produced in each region, × the volume of each flow from that region. Indirect and unknown flows get the national average, weighted by where untraced cocoa most likely comes from. `HOW_THE_MODEL_WORKS.md` explains the steps, and `INPUT_DATA.md` (section 7) lists the input files. The synthetic example includes made-up files in `data/synthetic_cote_divoire/deforestation_metrics/`.
