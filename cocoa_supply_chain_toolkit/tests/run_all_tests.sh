#!/bin/sh
# Run every test. From the toolkit's top folder:  sh tests/run_all_tests.sh
set -e
echo "== 1. Model results as expected (example data, and data with every special case)"
Rscript tests/test_model_results.R
echo "== 2. The country template works for a country without the special cases"
Rscript tests/test_new_country.R
echo "== 3. Company names in the supplier links are cleaned like customs names"
Rscript tests/test_buyer_names.R
echo "== 4. Deforestation exposure"
Rscript tests/test_exposure.R
echo "== 5. Earth Engine post-processing"
python3 tests/test_earth_engine_exports.py
echo "== 6. Farmer-number estimates"
python3 tests/test_farmer_numbers.py
echo "== 7. Supplier-map tools and spreadsheet templates"
python3 tests/test_supplier_map_tools.py
echo "== 8. End-to-end run of the example with summaries (20 draws)"
OUT="$(mktemp -d)"
MODEL_N_DRAWS=20 MODEL_OUTPUT_DIR="$OUT" Rscript run_model.R > "$OUT/log.txt" 2>&1
MODEL_OUTPUT_DIR="$OUT" Rscript results_by_exporter_and_destination.R > /dev/null 2>&1
for f in supply_chains_cote_divoire_2024.csv supply_chains_cote_divoire_2024_with_deforestation.csv summaries/by_exporter.csv; do
  test -s "$OUT/$f" && echo "PASS  wrote $f" || { echo "FAIL  $f missing (see $OUT/log.txt)"; exit 1; }
done
echo "== 9. Every worked example, from the synthetic raw inputs"
sh tests/test_examples.sh
echo "All tests passed."
