# 3. Reading the results

## Output files

After a run, `trase/models/orvessa/candy/2017/` contains:

| Path | Contents |
|---|---|
| `downloaded/` | Copies of the raw input files, exactly as read |
| `prepared/` | Cleaned inputs: renamed and type-checked columns, placeholder rows added |
| `results/results.csv` | **The model output**: one row per flow, Trase-style columns |
| `results/flows.csv` | The model's internal flow table, with all working columns |

The folder is recreated on every run and is ignored by git.

## `results.csv` columns

Semicolon-separated. One row per flow; a customs declaration that was split appears as
several rows.

| Column | Meaning |
|---|---|
| COUNTRY_OF_ORIGIN | Always `ORVESSA` |
| MUNICIPALITY_TRASE_ID_PROD | **Municipality of production** found by the model, e.g. `OV-104`. `OV-UNKNOWN` if not traced |
| PORT_OF_EXPORT | Port the shipment left from (`NONE` for domestic flows) |
| EXPORTER | Name of the exporting asset (`UNKNOWN` for domestic flows) |
| EXPORTER_TAX_ID | Asset ID of the exporter (`666` is the placeholder for domestic flows) |
| IMPORTER | Importing company |
| COMPANY | Company that owns the exporting asset |
| COUNTRY_OF_DESTINATION | Where the goods went; `ORVESSA` for domestic consumption |
| VOLUME_RAW | Tonnes |
| FOB | Value in USD (0 for domestic flows) |
| HS6 | Product code (`990001` candyflower, `990002` candy, `000000` domestic) |
| YEAR | 2017 |
| LEVEL | Level of the exporting asset: 1 farm, 2 silo, 3 factory, 5 other, 0 none |
| STORAGE | Municipality code of the hub chosen by the decision tree (`0` = none) |
| BRANCH | Which decision-tree branch handled the flow (see below) |
| TERRITORIAL_DEFORESTATION | Hectares of deforestation attributed to the flow |
| STATUS | `SOLVED` (origin found) or `UNKNOWN` |

## The summary tables

`run_orvessa.py` prints volume by branch:

| Status | Branch | Volume (t) | Share |
|---|---|---:|---:|
| SOLVED | 2 - Candy storage is logistic Hub | 440 | 34% |
| UNKNOWN | 5 - Unknown | 260 | 20% |
| SOLVED | DOMESTIC DEMAND | 230 | 17% |
| SOLVED | 1 - Asset linked to production | 210 | 16% |
| SOLVED | 3.1 - Link to level 3 asset in known municipality | 180 | 14% |

Read this table as a **quality indicator**. In a real model you would want the
`UNKNOWN` share as small as possible: here a fifth of the volume (the three office
exporters) cannot be traced to a municipality. These flows still carry an *estimate*
of deforestation (see [step 4](2-how-the-model-works.md#step-4-deforestation)), but no
location.

It also prints deforestation by destination:

| Destination | Deforestation (ha) | Volume (t) | ha / t | Untraced (t) |
|---|---:|---:|---:|---:|
| Licoricia | 2,311 | 485 | 4.8 | 160 |
| Chocolatia | 1,335 | 155 | 8.6 | 0 |
| Caramelia | 1,085 | 150 | 7.2 | 0 |
| Bonbonia | 1,061 | 285 | 3.7 | 100 |
| Orvessa (domestic) | 758 | 230 | 3.3 | 0 |
| Pralinia | 200 | 20 | 10.0 | 0 |

Compare Chocolatia and Bonbonia. Chocolatia imports about half as much as Bonbonia
but is linked to more deforestation: 8.6 ha per tonne against 3.7. Two things explain
the difference:

- **Where it sources from.** All of Chocolatia's candyflower is traced to the north
  (Gumdrop Hills, Caramel Creek, Nougat Valley), where deforestation per tonne is
  7–10 ha/t. Bonbonia's largest traced supply is from Licorice Lake, at 2.3 ha/t.
- **How much is estimated.** 100 t of Bonbonia's 285 t come through an office and
  can't be traced. They carry 330 ha at the unclaimed pool's average intensity
  (3.3 ha/t). That figure is an estimate: if those shipments really came from Gumdrop
  Hills, they would carry three times as much.

Separating these two things is the whole point of supply-chain mapping. Two importers
of the same commodity can carry very different risk, and you always have to check how
much of each importer's figure rests on traced flows and how much on estimates.

## Useful ways to slice the results

In Python:

```python
import pandas as pd

df = pd.read_csv("trase/models/orvessa/candy/2017/results/results.csv", sep=";")

# deforestation per tonne, by importer
by_importer = df.groupby("IMPORTER")[["VOLUME_RAW", "TERRITORIAL_DEFORESTATION"]].sum()
by_importer["ha_per_t"] = by_importer["TERRITORIAL_DEFORESTATION"] / by_importer["VOLUME_RAW"]

# which municipalities supply each exporter?
df.pivot_table(
    index="EXPORTER", columns="MUNICIPALITY_TRASE_ID_PROD",
    values="VOLUME_RAW", aggfunc="sum", fill_value=0,
)
```

Or, during a run, use the engine's report helper on any column:

```python
sc.flow_report_by_attribute("vol", ["company", "country"])
```

## Known limitations

Orvessa is kept simple on purpose. Its shortcuts are the same ones real models must
deal with:

1. **Untraced exports get an average, not a location.** The 260 t exported by
   offices carry the unclaimed pool's average intensity, 3.3 ha/t. It is the best
   estimate the data allows, but the pool ranges from 0 ha/t (Peppermint Point,
   Sherbet Shore) to 10 ha/t (Gumdrop Hills), so the true figure for any single
   shipment could be anywhere in that range.

2. **Untraced exports and domestic demand share the pool in the same proportions.**
   The model has no information to tell them apart, so it assumes both draw on each
   municipality in proportion to its unclaimed production. In reality the domestic
   market might be supplied mostly from nearby farms, and exporters from the
   municipalities with the best roads to the ports.

3. **Shortest distance is a strong assumption.** Real trade follows contracts,
   ownership and prices, not only distance. Branch 3.1's "same company's nearest silo"
   rule partly reflects this, but the LP itself only knows about kilometres.

4. **One year, no stocks.** Candyflower harvested in 2016 and exported in 2017 is
   ignored.

5. **Lossless processing.** Real conversions lose mass (for example, 1 t of soybeans
   gives about 0.8 t of soy meal). Real models convert everything to an equivalent of
   the raw commodity before comparing volumes.

---

Previous: [2. How the model works](2-how-the-model-works.md) · Next: [4. Building your own model](4-building-your-own-model.md)
