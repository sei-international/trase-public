# 1. The scenario

## Orvessa

Orvessa is an island somewhere in the Pacific with a climate perfectly suited to
*candyflower* plantations. Candyflowers produce *candyfruit*, which can be refined
into candy. International demand for both raw candyflower and candy is high, and
plantations are expanding into Orvessa's ancient, highly biodiverse rainforest.

To improve transparency, the Orvessa government publishes:

- the island's municipalities,
- candyflower production and attributable deforestation per municipality,
- a register of the assets used in the supply chain (farms, silos, factories, offices),
- road distances between municipalities,
- customs declarations for every export shipment in 2017.

Deforestation is only known **per municipality**, so to link a shipment to
deforestation we need to know which municipality its candyflower came from. Customs data
records the *exporter*, not the place of production. Bridging that gap is the job of the
model.

## Simplifying assumptions

1. Candyflower is grown on farms that each sit entirely within one municipality, and is
   harvested once a year.
2. After harvest the candyflower *may* go to a storage silo, and *may* then go to a
   factory where it becomes candy. Either step can be skipped.
3. Everything happens within one calendar year: no stock is carried over.
4. Processing is lossless: 1 tonne of candyflower becomes 1 tonne of candy.
5. Candyflower travels the shortest overall distance from farm to export hub. This
   is the assumption behind the linear programming step.
6. Whatever is not exported is consumed in Orvessa.

## The island

Orvessa has three states and ten municipalities. Production and deforestation are
concentrated in the north (S1); the south-east (S3) has the factories.

| State | Code | Municipality | Production (t) | Deforestation (ha) | Assets (level) |
|---|---|---|---:|---:|---|
| S1 | 101 | Gumdrop Hills | 150 | 1,500 | Farm (1) ×2, Silo (2), Factory (3) |
| S1 | 102 | Toffee Flats | 200 | 1,600 | Farm_Green1, Silo_Green1, Farm ×2, Factory, Office |
| S1 | 103 | Nougat Valley | 175 | 1,300 | Farm_Green2, Silo_Green2, Silo |
| S1 | 104 | Caramel Creek | 125 | 1,000 | Farm_Black1, Silo_Black1, Farm |
| S2 | 201 | Fudge Falls | 225 | 500 | Farm_Red1, Silo, Farm |
| S2 | 202 | Marzipan Marsh | 200 | 450 | Farm_Red2, Silo_Red1, Fact_Red1, Farm |
| S2 | 203 | Licorice Lake | 175 | 400 | Farm_Black2, Farm, Office |
| S3 | 301 | Peppermint Point | 50 | 0 | Fact_Green1, Fact_Black1, Farm, Office |
| S3 | 302 | Sherbet Shore | 25 | 0 | Fact_Green2, Farm, Silo |
| S3 | 303 | Lollipop Landing | 0 | 0 | Factory, Silo |
| | | **Total** | **1,325** | **6,750** | |

Each state ships through its own port: **Port Sprinkle** (S1), **Port Treacle** (S2)
and **Port Praline** (S3).

### Companies

Three large companies own assets in several municipalities:

| Company | Farms | Silos | Factories |
|---|---|---|---|
| Green (100) | Toffee Flats, Nougat Valley | Toffee Flats, Nougat Valley | Peppermint Point, Sherbet Shore |
| Red (200) | Fudge Falls, Marzipan Marsh | Marzipan Marsh | Marzipan Marsh |
| Black (300) | Caramel Creek, Licorice Lake | Caramel Creek | Peppermint Point |

Many smaller companies (`Comp_123` … `Comp_168`) own a single asset each. Three of these
(`Comp_166`, `Comp_167`, `Comp_168`) own only an **office** (level 5): they trade
candy but own no farm, silo or factory.

### Trade

17 customs declarations record 1,095 t exported to five (fictional) countries:
Chocolatia, Pralinia, Bonbonia, Caramelia and Licoricia. That leaves 230 t of the
1,325 t produced for domestic consumption.

## Input files

All raw data lives in `trase/models/orvessa/candy/data/`. Files are semicolon-separated
unless noted.

### `municipalities.csv`

| Column | Type | Meaning |
|---|---|---|
| name | text | Municipality name |
| code | integer | Unique municipality code (first digit = state) |
| state | text | State (S1, S2, S3); not used by the model |
| trase_id | text | Stable public identifier, e.g. `OV-101` |

### `production_2017.csv`

| Column | Type | Meaning |
|---|---|---|
| municipality | text | Municipality name |
| production_tonnes | integer | Candyflower harvested in 2017 |
| deforestation_ha | number | Deforestation attributable to candyflower in 2017 |

### `assets.csv`

| Column | Type | Meaning |
|---|---|---|
| identifier | integer | Unique asset ID (also used as the exporter's tax ID) |
| name | text | Asset name |
| municipality | integer | Municipality code where the asset is located |
| level | integer | 1 = farm, 2 = storage silo, 3 = factory, 5 = other (e.g. office) |
| company | text | Owning company |

### `distances.csv` (comma-separated)

| Column | Type | Meaning |
|---|---|---|
| origin | integer | Municipality code |
| destination | integer | Municipality code |
| distance_km | integer | Road distance between the two municipalities' centres |

Every pair of municipalities is listed, in both directions.

### `customs_2017.csv`

One row per export shipment.

| Column | Type | Meaning |
|---|---|---|
| hs6 | text | Product code: `990001` raw candyflower, `990002` candy (fictional codes) |
| exporter | integer | Asset ID of the last known asset the goods passed through |
| municipality | integer | Municipality of the exporter. The model ignores this column: it is the exporter's address, not the place of production |
| volume_tonnes | number | Shipment volume |
| fob_usd | number | Shipment value (free on board) |
| country | text | Destination country |
| port | text | Port of export |
| importer | text | Importing company |

---

Next: [2. How the model works](2-how-the-model-works.md)
