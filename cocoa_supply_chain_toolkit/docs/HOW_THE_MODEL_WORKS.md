# How the model works

This walks through the model in plain language. Terms in *italics* are explained in [`GLOSSARY.md`](GLOSSARY.md). Each step corresponds to one function in `model/R/model_steps.R`, named `stepNN_...`, and `model/R/run_supply_chain_model.R` calls them in order. The settings that differ between countries are written in `code font` and live in `countries/<country>/config.R`.

## The question

Customs records show who exported a country's cocoa and where it went, but not where in the country it was grown. The model fills that gap. For each export flow (exporter → destination country → product), it estimates how much cocoa came from each **cooperative**, and from each **region** (the cooperative's location; departments in Côte d'Ivoire).

This is the approach Trase calls SEI-PCS ("Spatially Explicit Information on Production to Consumption Systems"). The Côte d'Ivoire cocoa version is described in Renier et al. (2023). This toolkit implements it so that it works for other countries, with Côte d'Ivoire 2024 as the worked example.

## The key idea

Many cocoa traders publish lists of the cooperatives they buy from, often with the number of farmers in each. The model combines four things:

- **Who buys from whom.** Company disclosures of their suppliers, compiled into a *supplier map*.
- **How big each cooperative is.** The number of farmers, disclosed or estimated.
- **How much a farm produces.** Farm-level production figures from a survey of the country's cocoa farmers (for Côte d'Ivoire, the KIT survey published in 2018).
- **What each trader actually exported.** Customs records.

From these it estimates how much each trader bought from each cooperative. Whatever the trader exported beyond that cannot be traced to a specific place.

Several of these quantities are uncertain, so the model runs as a **Monte Carlo simulation** with 1000 draws by default. Each draw uses different random samples of farm sizes and farm production. The result table holds the mean over all draws. The full set of draws is saved too, so uncertainty ranges can be computed (`results_by_exporter_and_destination.R` does this).

## Published documentation

Trase's published documentation describes the method in more depth, so read it alongside this file:

- **The model.** Trase (2026), *SEI-PCS Côte d'Ivoire cocoa v1.2 supply chain map: Data sources and methods*, https://doi.org/10.48650/3KGC-VB46.
- **The cooperative data.** Guye (2024), *Ivorian Cocoa Cooperatives and their Buyers (IC2B)*, https://doi.org/10.14428/DVN/YBWJOR (CC BY 4.0). The Côte d'Ivoire supplier map is derived from it.
- **Deforestation exposure.** Trase (2022), *Commodity deforestation exposure and carbon emissions assessment*, https://doi.org/10.48650/GE7V-Q043.

This file describes **what the code does**.

## Three kinds of sourcing in the result

Every row of the result belongs to one of three categories, given in `SOURCING_TYPE`:

| `SOURCING_TYPE` | `REGION_ID` | Meaning |
|---|---|---|
| **DIRECT** | the region, e.g. `CI-050101` | Traced to a named cooperative or licensed buyer in that region |
| **INDIRECT** | `CI-INDIRECT` (`ids$indirect_region_id`) | The exporter disclosed some suppliers, but exported more than those suppliers can explain. The rest came through intermediaries (*traitants*, *pisteurs*, other exporters) or undisclosed suppliers. |
| **UNKNOWN** | `CI-UNKNOWN` (`ids$unknown_region_id`) | The exporter disclosed no suppliers at all |

Companies that publish supplier lists but are not exporters (chocolate makers, retailers, certification schemes), or whose exports in customs data are far below what they say they source, are marked `BUYER_IS_TRADER = FALSE` in the supplier map. Their lists still help locate cooperatives, but do not count as anyone's direct sourcing. In Côte d'Ivoire these are Albert Heijn, Alfred Ritter, Alter Eco, Blommer, Colruyt, Ecookim, Ferrero, Hershey, Mars, Mondelēz, Nestlé, Puratos, Tony's Chocolonely and Valrhona.

## Step by step

### Step 0: Prepare inputs (`read_inputs()` and `prepare_inputs()`)

The country's `read_inputs()` reads the files and renames columns to the standard format (`docs/INPUT_DATA.md`). `prepare_inputs()` then:

- converts each shipment's weight to **cocoa bean equivalent** (BEQ), using ICCO factors. For example, 1 t of cocoa butter = 1.33 t of beans. This makes beans, paste, butter and powder comparable.
- drops cocoa shells and waste (HS 180200).
- **cleans company names.** Customs data spell the same company dozens of ways. The rule table `rules/company_group_rules.csv` maps each spelling to a *company group* (`EXPORTER_GROUP` in the result). The original spelling is kept as `EXPORTER`. See `model/R/company_names.R`.
- **cleans the company names in the supplier links the same way** (`standardise_buyer_names()`), so that a disclosure by "OFI" matches "OLAM" in customs. A link whose buyer lists several companies ("BARRY CALLEBAUT + CARGILL") becomes one link per company. If a cooperative then has two links to the same company, one is kept.
- **recognises cooperatives that export directly.** The rule table `rules/exporting_cooperative_rules.csv` renames them `<ACRONYM> (COOPERATIVE)` (`exporting_cooperative_tag`).
- gives every cooperative and licensed buyer an ID (`ids`).

Inside the model steps, columns keep short working names (for example `GEOCODE` for the region code and `COOPACRONYM` for the supplier's short name). `prepare_inputs()` translates the input names into them, and `plain_output()` in `model/R/summarise_results.R` translates them back for the result table.

### Step 0.1: Use the importer to re-attribute some shipments (`step01_attribute_shipments`)

Customs data also name the foreign buyer (the importer). Sometimes a shipment is exported by a company that published nothing, but bought abroad by a trader who *did* publish its suppliers. In that case the importer is often the real owner of the supply chain, so the shipment is counted under the importer. The conditions are:

- the exporter did not disclose, and
- the importer is a disclosing trader, *or* a signatory of a sector commitment (`commitment_signatories`; in Côte d'Ivoire, the Cocoa & Forests Initiative) that also exports from the country itself.

When two disclosing traders trade with each other, the exporter keeps the shipment. As the published documentation notes, this means results under-represent the volumes of exporting cooperatives and non-disclosing traders that sell to disclosing traders, and give a fuller picture of disclosing traders.

Each shipment is also flagged as **potentially direct** if its exporter disclosed suppliers, or if the exporter is a cooperative or a union of cooperatives (`cooperative_unions`). Only these shipments can later receive traced volumes. Unions of cooperatives (ECOOKIM in Côte d'Ivoire) are treated as exporting cooperatives, not as disclosing traders, because their member cooperatives may also be disclosed by other companies.

### Steps 1–4: Build the list of supplier links

- **Steps 1–2** (`step02_disclosed_links`). Keep the supplier-buyer links that have a buyer.
- **Step 3** (`step03_licensed_buyer_links`). Add licensed buyers (*acheteurs agréés* in Côte d'Ivoire) whose name matches an exporter in customs data. They are registered intermediaries with a known region. Names that differ are mapped in `licensed_buyer_to_exporter`. In the Côte d'Ivoire 2024 data this step finds no matches, but it may be useful elsewhere. Countries without such a register can leave the table empty.
- **Step 4** (`step04_combine_links`). Add one placeholder "UNKNOWN" link per exporter. It will hold whatever cannot be traced. Links without a known region are dropped.

### Step 5: Number of farmers per link (`step05_farmers_per_link`)

Each link needs a size (number of farmers), with one value per Monte Carlo draw. The published documentation summarises this as "extrapolated from other links of the same cooperative, otherwise from the overall average link size". In the code, the second case is a random draw from all disclosed sizes, so the *average* over draws is the overall average.

- **Size disclosed by the trader:** the same value in every draw.
- **Size not disclosed by the trader, but known in another way:** filled in when the supplier map is built, before the model runs (`impute_farmer_numbers()` in `supplier_map/supplier_map_tools.py`). In order:
  1. the same trader's figure for this cooperative from another year (mean across years);
  2. otherwise, the mean of the figures other companies disclose for this cooperative (same year, then any year). Certification schemes such as Rainforest Alliance count as sources here but not as buyers.

  `impute_farmer_numbers()` also returns `NUM_FARMERS_EXTRAPOLATED` (the year's mean link size), for publishing a complete supplier map only. The model does not use it: it draws missing sizes itself (next point).
- **No size disclosed anywhere:** each draw picks a size at random from all disclosed cooperative-trader sizes.

### Step 6: Each cooperative's share of a trader's supply (`step06_link_shares`)

For each trader and draw, the model divides each cooperative's farmers by the trader's total farmers across all its disclosed cooperatives. This share is used later to split the trader's direct volume between its cooperatives.

### Step 7: Cocoa volume per link (`step07_link_volumes`)

For a link with *n* farmers, each draw picks *n* farms at random (with replacement) from the farm production survey and adds up their production. This gives a volume estimate that reflects how much farm output really varies. On average, it equals *n* × the survey's mean production per farm, which is how the published documentation describes it. In Côte d'Ivoire, the KIT survey has 441 farms, producing 17–5,800 kg a year (mean 1,225 kg, median 793 kg), spread evenly over the cocoa regions. Côte d'Ivoire uses the KIT survey (Tyszler et al. 2018). A new country needs a farm-level survey of annual cocoa production from that country.

### Step 8: Direct volume per trader, with a cap (`step08_direct_per_exporter`)

- The trader's **direct volume** is the sum of the volumes of all its links.
- **Cap.** Direct volume cannot exceed the trader's potentially-direct exports in customs data. Without the cap, a trader whose disclosures imply more cocoa than it exported would end up with negative indirect sourcing.
- **Direct proportion** = direct volume ÷ total exports.
- **Indirect volume** = total exports − direct volume. This goes on the trader's UNKNOWN link.
- **Value (CIF, USD)** is split in the same proportion as volume.

### Step 9: Split each trade flow into direct and remaining parts (`step09_trade_flows`)

Shipments are summed into **trade flows**: original exporter name × destination country × product code. This is the finest level kept in the output. Each flow is split as follows:

- **Direct part** = the flow's potentially-direct volume × the trader's direct share of its potentially-direct exports.
- **Remaining part** = everything else.

### Step 10: Allocate the direct part to cooperatives (`step10_allocate_to_suppliers`)

The direct part of each flow is shared among the trader's cooperatives in proportion to their farmer shares from Step 6. The remaining part stays on the UNKNOWN link.

### Step 11: Exporting cooperatives (`step11_exporting_coops`)

Cooperatives that export directly are handled differently. All their exports are traced to their own region. To make this work:

- Names in customs data are matched to cooperatives in the map by acronym. A few acronyms are shared by several cooperatives. Those cases are resolved by hand in `rules/exporting_cooperative_shared_acronyms.csv`.
- Unions of cooperatives (`cooperative_unions`; ECOOKIM in Côte d'Ivoire) have their exports split equally across their member cooperatives.
- If no cooperative exports directly, this step adds nothing.

After each run, check `diagnostics$exporters_that_may_be_cooperatives` (printed by `run_model.R`). It lists exporters that are neither known cooperatives nor disclosing companies, so you can spot cooperatives missing from the rules.

### Step 12: Combine (`step12_combine`)

The exporting-cooperative flows replace the generic flows for those exporters, so nothing is counted twice.

### Final step: Summarise and format (`finalise_output`, `plain_output`)

- Take the **mean over all draws** for each row.
- Convert bean-equivalent volume back to product weight (`PRODUCT_WEIGHT_KG`) using the same factors.
- Add region names, product names and IDs (`region_to_id`).
- Label untraced volume as **INDIRECT** if the exporter disclosed anything, and **UNKNOWN** otherwise (`SOURCING_TYPE`).
- Drop rows with zero volume. These arise when a trader's direct volume equals all its exports.
- Write the output table (`output_file`). The value column is named after `value_column_name`, for example `CIF_USD`.

## From the model to deforestation exposure (`model/R/deforestation_exposure.R`)

The model result gives volumes per region. The deforestation metrics give deforestation per region (`DEFORESTATION_METRICS.md`). These functions link them, following Renier et al. (2023, appendix Eq. 6) and Trase (2022):

1. **`untraced_region_weights()`.** For each region: production minus the volume traced to it (floored at 0), as a share of the national total. This is where untraced cocoa most likely comes from.
2. **`per_tonne_metrics()`.** Deforestation and degradation, emissions and cocoa area per tonne produced, per region and year. INDIRECT and UNKNOWN sourcing get the average across regions, weighted by step 1.
3. **`deforestation_exposure()`.** Each flow's volume (t) × the per-tonne figures of its region (or of INDIRECT/UNKNOWN).
4. Optional, when the inputs exist:
   - **`add_region_attributes()`** adds any attribute of the region, such as its ecoregion (UNKNOWN for indirect and unknown flows);
   - **`add_company_commitments()`** adds whether the exporter had a zero-deforestation commitment in force in the model year (its type, NONE, or UNKNOWN if the exporter is not in the table).

`run_exposure()` runs them all. `run_model.R` calls it after the model when the country's `read_inputs.R` defines `read_spatial_inputs()`, and writes `supply_chains_<country>_<year>_with_deforestation.csv`. The extra columns are listed in `INPUT_DATA.md`.

The cocoa map used for Côte d'Ivoire shows cocoa around 2019–2021. For later model years `run_exposure()` warns that recent cocoa expansion is missed (`cocoa_map_valid_until` in `config.R`).

`tests/test_exposure.R` checks each step.

## Using the results

`results_by_exporter_and_destination.R` (run it after `run_model.R`) writes three summary tables to `output/<country>/summaries/`:

- **`by_exporter.csv`**: exports, the share traced to a region, deforestation, emissions and cocoa land per company group, and a 95% range for the traced volume from the Monte Carlo draws;
- **`by_destination.csv`**: the same per importing country;
- **`by_region.csv`**: traced volume and deforestation per region.

Copy it to start your own analysis. Two things to keep in mind when reporting:

- **Deforestation exposure is an association, not attribution.** It says how much deforestation happened, per tonne, where a company's cocoa came from. It does not say the company caused it.
- **Most exposure is often indirect or unknown.** Those flows carry the national average per tonne, so differences between companies come mainly from their traced share.

## Built-in checks

After Steps 8, 9, 10 and 12, and again at the end, the code checks that total volume and total value still equal the customs totals, within 0.01%. If they don't, it stops. So traced, indirect and unknown always add up to total exports.

## Main assumptions and limitations

(See also the published documentation and Renier et al. 2023, which test several of these.)

- **Farmer numbers stand in for volume.** A cooperative's supply to a trader is assumed to scale with its number of farmers, and every farm is assumed to produce like a randomly drawn surveyed farm. Farm-level production varies a lot, and the KIT survey data were published in 2018, so they predate the 2024 season.
- **Disclosures are taken at face value.** They are not checked against volumes. Traders that disclose nothing contribute only "unknown" volume.
- **Location is the cooperative's region.** A cooperative's members may farm in neighbouring regions. Check it by comparing direct volumes with estimated regional production. Departments where traced volume exceeds production point to mislocated cooperatives or oversized links (Renier et al. 2023 test this for 2019).
- **Disclosed links are assumed to be all of a trader's direct sourcing**, and cooperatives that cannot be located are assumed to be distributed like those that can.
- **Value** is whatever customs report (CIF for Côte d'Ivoire 2024). Set `value_column_name` to match.
- **The Monte Carlo spread covers only some of the uncertainty.** It covers farm sizes and farm yields, not errors in the disclosures or in the name matching.

## Result columns

The columns of the result tables are listed in [`INPUT_DATA.md`](INPUT_DATA.md), section "Results".

## Where to look in the code

| If you want to… | Look at |
|---|---|
| change how company names are grouped | `countries/<country>/rules/company_group_rules.csv` |
| add a newly exporting cooperative | `rules/exporting_cooperative_rules.csv`, and `rules/exporting_cooperative_shared_acronyms.csv` if its acronym is shared |
| change the number of draws | `MODEL_N_DRAWS` (or `n_draws` in `config.R`) |
| change conversion factors | `commodities/cocoa/bean_conversion_factors.csv` |
| see how the supplier map is built | `supplier_map/` |
| change how deforestation is linked to flows | `model/R/deforestation_exposure.R`, `read_spatial_inputs()` in `countries/<country>/read_inputs.R` |

## References

- Renier, C. et al. (2023). Transparency, traceability and deforestation in the Ivorian cocoa supply chain. *Environmental Research Letters* 18, 024030.
- Tyszler, M., Bymolt, R. & Laven, A. (2018). Demystifying the cocoa sector in Ghana and Côte d'Ivoire. Harvard Dataverse. https://doi.org/10.7910/DVN/82TWZJ
