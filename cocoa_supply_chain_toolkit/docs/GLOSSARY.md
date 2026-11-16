# Glossary

Terms used in the code, the documentation and the result tables, in alphabetical order. Column names are in `CODE FONT`.

**Allocation period.** Deforestation in the years before a harvest is spread over the cocoa produced later. With a 15-year allocation period, cocoa exported in year *Y* carries the forest lost to cocoa over 15 years (from *Y*−19 to *Y*−4, with the 4-year *lag*). Columns ending in `_15Y` use it; columns ending in `_ANNUAL` use one year only. See `DEFORESTATION_METRICS.md`.

**Bean equivalent (`BEAN_EQUIVALENT_KG`).** Weight of cocoa beans needed to make a product. Customs report beans, paste, butter and powder by product weight; converting to bean equivalent makes them comparable. The factors (from ICCO) are in `commodities/cocoa/bean_conversion_factors.csv`; for example 1 t of cocoa butter = 1.33 t of beans.

**Buyer (`BUYER`).** In the supplier map, the company that says it buys from a supplier: the trader named in a disclosure if there is one, otherwise the company that published the disclosure. Certification schemes are never buyers.

**Cap.** A trader's directly traced volume cannot exceed what it exported in customs data. If its disclosed suppliers imply more cocoa than that, all its eligible exports count as direct and none as indirect (Step 8).

**Cocoa deforestation and degradation.** Undisturbed tropical moist forest that was lost, to deforestation or to degradation, where the cocoa map now shows cocoa. Degradation is included because shade trees in cocoa plots make many conversions look like degradation from space. Emissions count deforestation only.

**Cocoa land (`COCOA_LAND_HA`).** Area of cocoa plantation needed to grow a flow's volume: volume × the region's cocoa area per tonne produced.

**Commitment signatories (`rules/commitment_signatories.csv`).** Companies that signed a sector commitment (in Côte d'Ivoire, the Cocoa & Forests Initiative). They are treated like disclosing traders for importer re-attribution.

**Company group (`EXPORTER_GROUP`).** One name for all the subsidiaries and spellings of a company ("CARGILL WEST AFRICA", "CARGIL COCOA" → CARGILL). Set by the *company-name rules*.

**Company-name rules (`rules/company_group_rules.csv`).** Table of patterns that turn a company-name spelling into its group. Applied to exporters and importers in customs data and to buyers in the supplier map, so both sides use the same names. See "Regular expressions" in `INPUT_DATA.md`.

**Customs records (`trade`).** One row per export shipment: exporter, foreign buyer (importer), destination, product code, weight and value.

**Deforestation exposure.** Deforestation linked to a flow: its volume (t) × the deforestation per tonne produced in the region it came from. It describes an association between a trade flow and deforestation in its sourcing region, not proof that this trader caused this deforestation.

**Direct, indirect and unknown sourcing (`SOURCING_TYPE`).**
- **DIRECT**: traced to a named supplier (cooperative or licensed buyer) and its region, through a published supplier list or because a cooperative exported itself.
- **INDIRECT**: the exporter published suppliers, but exported more than those suppliers can explain. The rest came through intermediaries or unlisted suppliers, from unknown places.
- **UNKNOWN**: the exporter published no suppliers at all.

Indirect and unknown flows get the country's average deforestation per tonne, weighted by *untraced production*.

**Disclosure.** A company's published list of the cooperatives (or other suppliers) it buys from, often with farmer numbers and coordinates. Found in sustainability reports, supplier lists and online maps.

**Draw, Monte Carlo (`MODEL_N_DRAWS`).** The model repeats its random steps (farmer numbers that are not known, and farm production) many times; each repetition is a draw. The result table holds the mean over all draws; `intermediate/flows_with_draws_<year>.rds` holds every draw, from which uncertainty ranges are computed (`results_by_exporter_and_destination.R` does this).

**Exporting cooperative.** A cooperative that exports cocoa itself and therefore appears as an exporter in customs data. All its exports are traced to its own region. Recognised by `rules/exporting_cooperative_rules.csv`, which renames it `<SHORT NAME> (COOPERATIVE)`.

**Farm production survey (`farm_production`).** Annual cocoa production of a sample of farms. Turns numbers of farmers into volumes (Step 7). For Côte d'Ivoire, the KIT survey (Tyszler et al. 2018).

**Flow.** One row of the result table: an exporter (as named in customs) × destination country × product code × supplier and region.

**HS code (`HS6`, `HS_CODE`).** Harmonized System product code used in customs data. Cocoa products are in chapter 18: 1801 beans, 1803 paste, 1804 butter, 1805 powder; 1802 shells and waste are not modelled.

**Importer re-attribution.** When an exporter published no suppliers but sold to a foreign buyer that is a disclosing trader (or a commitment signatory that also exports from the country), the shipment is counted under that buyer (Step 0.1).

**Lag.** Years between clearing land and the first cocoa harvest (and the year the plantation becomes visible on the cocoa map). Default 4.

**Licensed buyer.** A registered cocoa intermediary with a known area of operation (in Côte d'Ivoire, *acheteurs agréés* registered with the Conseil du Café-Cacao). Optional input.

**Link.** One row of `supplier_links`: one supplier and one company that says it buys from it.

**Link size (`NUMBER_OF_FARMERS`).** Number of farmers in a supplier who sell to one buyer.

**Potentially direct shipment.** A shipment that can receive traced volume: its exporter (after re-attribution) published suppliers, or is a cooperative or union of cooperatives.

**Region (`REGION_CODE`, `REGION_ID`).** The sub-national unit the results are given for (departments in Côte d'Ivoire). `REGION_CODE` is the code in your input files; `REGION_ID` is the code written in the results and used by the deforestation tables (`config$region_to_id()` turns one into the other; they can be identical).

**Supplier (`SUPPLIER_NUMBER`, `SUPPLIER_ID`).** The first buyer of the cocoa with a known location: usually a cooperative, sometimes a warehouse or licensed buyer. `SUPPLIER_NUMBER` is the number you give it in the supplier map; `SUPPLIER_ID` is the ID written in the results (prefix from `config$ids` + number).

**Supplier map.** The two tables `supplier_links` and `suppliers`: which suppliers exist, where they are, and which companies buy from them. Built from disclosures (`supplier_map/`).

**Trader (`BUYER_IS_TRADER`).** A company that exports cocoa from the country and appears in customs data. Only links to traders count as direct sourcing.

**Union of cooperatives (`cooperative_unions` in `config.R`).** A network of cooperatives that exports on behalf of its members (ECOOKIM in Côte d'Ivoire). Its exports are split equally between its member cooperatives.

**Untraced production (`SHARE_OF_UNTRACED_PRODUCTION`).** For each region, production minus the volume traced to it (never below zero), as a share of the national total. Indirect and unknown flows most likely come from where this is large, so their deforestation per tonne is the regional average weighted by it.

**Value (`CIF_USD`, `FOB_USD`).** Shipment value as reported by customs. CIF includes freight and insurance to the destination; FOB does not. Set `value_column_name` in `config.R` to match your data.
