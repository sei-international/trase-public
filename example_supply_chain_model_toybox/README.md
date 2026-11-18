# Orvessa: a supply-chain mapping toybox

Orvessa is a small, made-up country that grows *candyflower* and exports it, and the
candy made from it, to the world. All of the data is synthetic and fits in five small
CSV files.

The repository contains a complete, runnable supply-chain model of Orvessa. It is
based on the engine and approach that [Trase](https://trase.earth) uses for real
commodities: **SEI-PCS** (Spatially Explicit Information on Production to Consumption
Systems). You can run it, read every line of it, change it and see what happens, with
no accounts, cloud storage or databases.

The question the model answers:

> For each export shipment, which municipality was the candyflower grown in, and how much
> of that municipality's deforestation should the shipment carry?

> **Disclaimer:** This is a simplified and adapted version of Trase's supply chain
> mapping code, designed for ease of use by the public. Orvessa, its companies and
> all of its data are fictional. Please note that the internal Trase code has
> differences. Also note that we do not use the same supply chain mapping methods
> between commodities and countries. Get an overview of Trase methodologies here:
> https://trase.earth/methodology

## Quick start

You need Python 3.10–3.13.

```bash
git clone <this repository>
cd orvessa-toybox
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_orvessa.py
```

The run takes a few seconds and ends with two summary tables and the location of the
results file:

```text
Volume (tonnes) by status and decision-tree branch:
                                                          sum percentage
status  branch
SOLVED  2 - Candy storage is logistic Hub                 440        34%
UNKNOWN 5 - Unknown                                       260        20%
SOLVED  DOMESTIC DEMAND                                   230        17%
        1 - Asset linked to production                    210        16%
        3.1 - Link to level 3 asset in known municipality 180        14%

Deforestation (ha) by destination country:
...
Results written to .../trase/models/orvessa/candy/2017/results/results.csv
```

To check that everything works as expected, run the tests:

```bash
pytest
```

To explore interactively in a notebook (optional):

```bash
pip install jupyterlab plotly
jupyter lab notebooks/orvessa_walkthrough.ipynb
```

## Where to read next

The docs assume you know the basics of supply-chain mapping: trade flows, exporters,
sourcing regions and the idea of attributing deforestation to trade.

| Document | What it covers |
|---|---|
| [1. The scenario](docs/1-the-scenario.md) | Orvessa, its supply chain, the assumptions and every input file |
| [2. How the model works](docs/2-how-the-model-works.md) | The four model steps, with one shipment traced from start to finish |
| [3. Reading the results](docs/3-reading-the-results.md) | Every column of `results.csv`, how to interpret it, and the model's known limitations |
| [4. Building your own model](docs/4-building-your-own-model.md) | How the engine works: definitions, preparation, `get` / `update`, conservation checks |
| [5. Exercises](docs/5-exercises.md) | Things to change and questions to answer, from easy to hard |

## What's in the repository

```text
orvessa-toybox/
├── run_orvessa.py                  # run the whole model
├── docs/                             # documentation (start here)
├── notebooks/
│   └── orvessa_walkthrough.ipynb   # the same run, step by step, with charts
├── tests/
│   ├── test_orvessa.py             # end-to-end test
│   └── data/ORVESSA_2017.csv       # expected results
└── trase/
    ├── models/orvessa/candy/       # ← the Orvessa model
    │   ├── data/                     #   raw synthetic input data
    │   ├── definition.py             #   declares datasets, columns, links, outputs
    │   ├── preparation.py            #   cleans raw data into model inputs
    │   ├── model.py                  #   the model logic
    │   ├── quality_assurance.py      #   checks on the results
    │   └── constants.py
    └── tools/                        # ← the engine (you rarely need to edit this)
        ├── etl/                      #   data preparation framework
        ├── sei_pcs/                  #   SupplyChain class, linear programming, joins
        └── utilities/                #   small helpers
```

The Python package is called `trase` so that the code reads like Trase's own
models, and the concepts carry over to them.

## Licence

GPL-3.0. See [LICENSE](LICENSE).
