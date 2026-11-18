# 2. How the model works

> The methods here are simplified for teaching. Trase's real models differ, and differ
> between commodities and countries: see https://trase.earth/methodology

## The pipeline

`run_orvessa.py` calls five methods on a `SupplyChain` object. Each one reads or
writes files under `trase/models/orvessa/candy/2017/`.

```text
 data/*.csv
     │  sc.preparation()        preparation.py    clean, rename, cast columns
     ▼
 2017/prepared/*.csv
     │  sc.load()               definition.py     load, type-check, resolve links
     ▼
 in-memory flows + reference data
     │  sc.run()                model.py
     │     1. decision_tree           which hub did each shipment come from?
     │     2. linear_programming      which municipalities supplied each hub?
     │     3. append_domestic_demand  add flows for production not exported
     │     4. embed_deforestation     share deforestation between flows
     │  sc.quality_assurance()  quality_assurance.py   sanity checks
     ▼
 sc.export_results()  →  2017/results/results.csv
```

Every customs declaration starts as one **flow**. As the model runs it fills in the
flow's columns (`branch`, `status`, `storage`, `municipality`, `deforestation`) and may
**split** one flow into several, for example when a shipment's candyflower came from
two municipalities. Volume (`vol`) and value (`fob`) are *conserved*: the engine
checks that splitting never creates or loses any.

A flow's `status` records its progress:

```text
UNKNOWN ──(decision tree finds a hub)──► TO LP ──(LP finds sources)──► SOLVED
   │
   └── stays UNKNOWN if no branch applies
```

## Step 1: decision tree

*Which storage hub did this shipment come from?*

Customs data only tells us the **last asset** the goods passed through before export.
The decision tree uses what we know about that asset to choose a **storage
municipality**: the place where candyflower was gathered before export. The model
calls it the *hub*.

| Branch | Exporting asset | Assumption | Hub |
|---|---|---|---|
| 1 | Farm (level 1) | The farm collected candyflower from its area | The farm's municipality |
| 2 | Silo (level 2) | The silo is a logistics hub for nearby farms | The silo's municipality |
| 3.1 | Factory (level 3) | Factories are supplied by their own company's silos | The municipality of the **same company's nearest silo** |
| 5 | Anything else (offices) | We know nothing about the sourcing | None: the flow stays `UNKNOWN` |

Branch 3.1 relies on the distance table. For `Fact_Green1` in Peppermint Point, company
Green owns silos in Toffee Flats (200 km away) and Nougat Valley (250 km away), so the
hub is **Toffee Flats**. A factory whose company owns no silos falls through to branch 5.

## Step 2: linear programming

*Which municipalities supplied each hub?*

Several hubs compete for the same farms. The model solves this as a **transportation
problem**:

- **Sources:** municipalities, each able to supply up to its production.
- **Sinks:** hubs, each needing the total volume of the shipments assigned to it in
  step 1.
- **Cost:** the distance between source and hub.

The solver finds the allocation that meets every hub's demand with the **minimum total
tonne-kilometres**. Each shipment is then split across its hub's suppliers in
proportion: if a hub got 74% of its candyflower from municipality A, every shipment
from that hub is 74% from A.

The solver is CBC, which ships with the PuLP package. Set `TRASE_LP_VERBOSE=1` to see its
log.

The solution for 2017:

| Hub | Demand (t) | Supplied by |
|---|---:|---|
| Gumdrop Hills | 75 | Gumdrop Hills 75 |
| Toffee Flats | 235 | Toffee Flats 200, Fudge Falls 35 |
| Nougat Valley | 110 | Nougat Valley 110 |
| Caramel Creek | 170 | Caramel Creek 125, Nougat Valley 45 |
| Marzipan Marsh | 120 | Marzipan Marsh 120 |
| Licorice Lake | 125 | Licorice Lake 125 |

Toffee Flats and Caramel Creek need more than they grow, so the LP pulls in
candyflower from neighbouring municipalities that have some to spare. When two
sources are equally far away, the solver may pick either; both give the same total
distance.

## Step 3: domestic demand

*What happened to the candyflower nobody exported, and where did the untraced exports
come from?*

After the LP, each municipality has some production that traced exports did not use.
Call this the **unclaimed pool**:

```text
unclaimed = production − volume sent to hubs by the LP
```

| Municipality | Production (t) | Used by LP (t) | Unclaimed (t) |
|---|---:|---:|---:|
| Gumdrop Hills | 150 | 75 | 75 |
| Toffee Flats | 200 | 200 | 0 |
| Nougat Valley | 175 | 155 | 20 |
| Caramel Creek | 125 | 125 | 0 |
| Fudge Falls | 225 | 35 | 190 |
| Marzipan Marsh | 200 | 120 | 80 |
| Licorice Lake | 175 | 125 | 50 |
| Peppermint Point | 50 | 0 | 50 |
| Sherbet Shore | 25 | 0 | 25 |
| **Total** | **1,325** | **835** | **490** |

The 490 t pool is exactly what is needed for the two groups of flows whose origin we
don't yet know:

- **260 t of untraced exports** (the office exporters, branch 5), and
- **230 t of domestic consumption** (production − exports).

The model assumes both came from the pool **in proportion to each municipality's
unclaimed volume**. Fudge Falls holds 190 / 490 = 38.8% of the pool, so it supplies
38.8% of domestic demand (89.2 t) and, implicitly, 38.8% of the untraced exports.
Toffee Flats and Caramel Creek have nothing left, so they supply neither.

The model adds one `DOMESTIC DEMAND` flow per municipality with unclaimed production,
with destination `ORVESSA`. Untraced exports stay as they are (municipality `UNKNOWN`):
we know which pool they came from, but not which municipality any single shipment
came from.

Without domestic flows, step 4 would hand **all** of a municipality's deforestation to
its exports, overstating the impact of trade.

## Step 4: deforestation

*How much deforestation does each flow carry?*

Each municipality has a **deforestation intensity**: its deforestation divided by its
production, in hectares per tonne. Gumdrop Hills: 1,500 ha / 150 t = 10 ha/t.

- **Flows with a known municipality** (traced exports and domestic demand):

  ```text
  flow deforestation = flow volume × intensity of its municipality
  ```

- **Untraced exports** came from the unclaimed pool, so they carry the pool's average
  intensity, weighted by unclaimed volume. For 2017 that is **3.30 ha/t**:

  ```text
  pool intensity = Σ (unclaimed volume × intensity) / Σ unclaimed volume
  ```

Because traced exports, domestic demand and the untraced share together use exactly
each municipality's production, all 6,750 ha are attributed, with nothing counted twice.
`quality_assurance.py` checks this.

## Worked example: one shipment, start to finish

Customs row: **`Fact_Black1` (asset 300004, Peppermint Point) exports 70 t of candy to
Licoricia via Port Praline.**

1. **Decision tree.** `Fact_Black1` is a factory (level 3), so branch 3.1 applies. Its
   owner, company Black, has one silo: `Silo_Black1` in **Caramel Creek**. That becomes
   the hub. Status: `TO LP`.

2. **Linear programming.** The Caramel Creek hub must supply this shipment (70 t) and
   `Silo_Black1`'s own export (100 t), 170 t in all. Caramel Creek grows only 125 t, so
   the LP adds 45 t from Nougat Valley, a neighbour 100 km away with spare candyflower.
   The shipment is split in the same proportions:

   | Source | Share | Volume |
   |---|---:|---:|
   | Caramel Creek | 125 / 170 = 73.5% | 51.47 t |
   | Nougat Valley | 45 / 170 = 26.5% | 18.53 t |

3. **Domestic demand.** Does not change this flow. The LP used all of Caramel Creek's
   production, so it supplies no domestic demand. Nougat Valley has 20 t unclaimed and
   supplies 9.39 t of domestic flow.

4. **Deforestation.**
   - Caramel Creek: 1,000 ha / 125 t = 8.00 ha/t. The 51.47 t part carries **411.8 ha**.
   - Nougat Valley: 1,300 ha / 175 t = 7.43 ha/t. The 18.53 t part carries **137.6 ha**.

One customs row has become two result rows: 70 t of candy to Licoricia carrying 549.4 ha
of deforestation, traced to two municipalities. You can see both rows in
`results.csv` (filter `EXPORTER_TAX_ID == 300004`).

---

Previous: [1. The scenario](1-the-scenario.md) · Next: [3. Reading the results](3-reading-the-results.md)
