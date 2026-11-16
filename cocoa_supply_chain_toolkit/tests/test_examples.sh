#!/bin/sh
# Run every worked example on the synthetic raw inputs, in a copy of the
# toolkit, so nothing in your folder is changed.
# From the toolkit's top folder:  sh tests/test_examples.sh
set -e
ROOT="$(pwd)"
WORK="$(mktemp -d)"
cp -r "$ROOT" "$WORK/toolkit"
cd "$WORK/toolkit"
LOG="$WORK/log.txt"
ok() { echo "PASS  $1"; }
run() {  # run <label> <command...>; stop with the log if it fails
  label="$1"; shift
  if "$@" >> "$LOG" 2>&1; then ok "$label"; else echo "FAIL  $label (see $LOG)"; tail -20 "$LOG"; exit 1; fi
}

run "synthetic raw inputs generated" python3 data/make_synthetic_raw_inputs.py
run "supplier map, steps 1-5, from fake company disclosures" \
    python3 supplier_map/build_supplier_map_cote_divoire_2024.py
run "supplier map passes check_model_tables" python3 -c "
import sys; sys.path.insert(0, 'supplier_map')
import pandas as pd, geopandas as gpd, supplier_map_tools as smt
d = 'data/synthetic_raw_inputs'
links = pd.read_csv(d + '/supplier_map/supplier_links_2024.csv')
links = links[links.YEAR == 2024]
sup = pd.read_csv(d + '/supplier_map/suppliers_2024.csv')
codes = gpd.read_file(d + '/regions/departments.geojson')['LVL_4_CODE']
problems = smt.check_model_tables(links, sup[sup.SUPPLIER_NUMBER.isin(links.SUPPLIER_NUMBER)], codes)
sys.exit(1 if [p for p in problems if 'not in suppliers' not in p] else 0)"
run "customs cleaning" Rscript input_preparation/trade/clean_customs_cote_divoire_2024.R
run "licensed buyers located" Rscript input_preparation/licensed_buyers/locate_licensed_buyers_cote_divoire.R
run "farm production from the (fake) KIT survey" Rscript -e \
    'rmarkdown::render("input_preparation/farm_production/farm_production_from_kit_survey.Rmd", knit_root_dir = getwd(), output_dir = tempdir(), quiet = TRUE)'
run "Earth Engine exports reshaped" python3 deforestation_metrics/reshape_earth_engine_exports.py --country ci \
    --input-dir data/synthetic_raw_inputs/earth_engine_exports --output-dir data/synthetic_raw_inputs/deforestation_metrics \
    --cocoa-area-file data/synthetic_raw_inputs/earth_engine_exports/cocoa_area_ci_v1.csv \
    --cocoa-production-file data/synthetic_raw_inputs/earth_engine_exports/cocoa_production_ci_v1.csv
run "regions prepared for Earth Engine" python3 deforestation_metrics/prepare_regions_for_earth_engine.py \
    data/synthetic_cote_divoire/regions/departments.geojson "$WORK/regions.zip"
for f in customs/cocoa_exports_2024.csv licensed_buyers/licensed_buyers_2021.csv farm_survey/kit_farm_production.csv \
         supplier_map/supplier_links_2024.csv deforestation_metrics/cocoa_deforestation_by_region.csv; do
  test -s "data/synthetic_raw_inputs/$f" && ok "wrote $f" || { echo "FAIL  $f missing"; exit 1; }
done
run "model + deforestation (20 draws)" env MODEL_N_DRAWS=20 MODEL_OUTPUT_DIR="$WORK/output" Rscript run_model.R
run "summary tables" env MODEL_OUTPUT_DIR="$WORK/output" Rscript results_by_exporter_and_destination.R
if Rscript -e 'quit(status = !all(sapply(c("rmarkdown", "kableExtra", "ggpubr", "viridis"), requireNamespace, quietly = TRUE)))' 2>/dev/null; then
  run "quality-check report" env MODEL_OUTPUT_DIR="$WORK/output" Rscript -e \
      'rmarkdown::render("countries/cote_divoire/reports/quality_checks_2024.Rmd", knit_root_dir = getwd(), output_dir = tempdir(), quiet = TRUE)'
else
  echo "SKIP  quality-check report (report packages not installed)"
fi
echo "All examples ran."
