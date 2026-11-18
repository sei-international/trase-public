# Orvessa candy model

A toy SEI-PCS model mapping Orvessa's candyflower and candy exports back to their
municipality of production, and attributing deforestation to each flow.

> **Disclaimer:** This is a simplified and adapted version of Trase's supply chain
> mapping code, designed for ease of use by the public. Orvessa, its companies and
> all of its data are fictional. Please note that the internal Trase code has
> differences. Also note that we do not use the same supply chain mapping methods
> between commodities and countries. Get an overview of Trase methodologies here:
> https://trase.earth/methodology

Run it from the repository root:

```bash
python run_orvessa.py
```

## Files

| File | Role | Read it to learn… |
|---|---|---|
| `data/` | Raw synthetic inputs | what the government publishes ([data dictionary](../../../../docs/1-the-scenario.md#input-files)) |
| `definition.py` | Declares datasets, columns, links and the results layout | how the engine knows what to load |
| `preparation.py` | Cleans `data/` into `2017/prepared/` | how raw data becomes model input |
| `model.py` | Decision tree → linear programming → domestic demand → deforestation | the actual supply-chain logic |
| `quality_assurance.py` | Checks run after the model | what "a correct result" means |
| `constants.py` | Placeholder IDs and the country name | |
| `2017/` | Created on each run: `downloaded/`, `prepared/`, `results/` | |

The full explanation is in [docs/2-how-the-model-works.md](../../../../docs/2-how-the-model-works.md).
