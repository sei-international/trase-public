# 4. Building your own model

This page explains how the engine works, so you can change the Orvessa model with
confidence or write a new model from scratch. Read it with the Orvessa files open
beside you.

## Where models live

`SupplyChain("orvessa/candy", 2017)` looks for a folder
`trase/models/orvessa/candy/` containing these files:

| File | Required? | Called by | Must define |
|---|---|---|---|
| `definition.py` | yes | `SupplyChain(...)` | module-level variables (see below) |
| `preparation.py` | no | `sc.preparation()` | `preparation(context)` |
| `model.py` | yes, for `sc.run()` | `sc.run()` | `run(supplychain)` |
| `quality_assurance.py` | no | `sc.quality_assurance()` | `run(supplychain)` |

`preparation.py` and `quality_assurance.py` may also sit one folder up (e.g.
`trase/models/orvessa/`), where they are shared by every commodity in that country.

Scripts are reloaded on every call, so you can edit `model.py` and call `sc.run()`
again in a notebook without restarting it.

## `definition.py`: declaring the data

The definition says *what* data exists; it contains no logic.

```python
from trase.tools.sei_pcs.definition import Dataset, c, e

datasets = {                       # reference tables
    "asset": Dataset([
        c("identifier", int),
        c("municipality", link="municipality.code"),   # foreign key
        ...
    ]),
}
constraints = {...}                # same as datasets; used for production, costs
flows = [                          # the customs data
    c("vol", float, conserve=True),
    c("asset", link="asset.identifier"),
    c("status", value="UNKNOWN"),  # not in the input: added with a default
    ...
]
flows_export = [                   # layout of results.csv
    e("VOLUME_RAW", "vol"),
    e("EXPORTER", "asset.name"),   # linked columns use dot notation
    ...
]
```

Options for `c(name, type=str, ...)`:

| Argument | Effect |
|---|---|
| `type` | `str`, `int`, `float` or `bool`; the column is cast and checked on load |
| `link="dataset.column"` | foreign key. On load the engine checks every value exists in the target, then joins the target's columns in as `name.column` |
| `key=True` | part of the dataset's unique key; duplicates raise an error |
| `value=...` | column is not in the input file; it is created with this default |
| `conserve=True` | totals must not change during `update()` (see below) |
| `validate=...` | extra validation, e.g. `Code(6)` for six-digit codes |

### Following links

Links chain. Because a flow links to an asset, and an asset links to a municipality,
`sc.get("flows")` contains `asset.municipality.name` with no merges on your part. If a
flow column such as `municipality` links on `municipality.name`, you can **set** it by
writing `municipality.name` and calling `update()`; the engine looks up the matching
code for you. `model.py` does this with `storage.name` and `municipality.name`.

## `preparation.py`: from raw files to model inputs

Each input gets a `Preprocessor` subclass:

```python
class Production(Preprocessor):
    source_path = ".../data/production_%YEAR%.csv"  # %YEAR% is substituted
    outname = "production.csv"                       # must match the definition
    columns = [
        Column("municipality"),
        Column("production_tonnes", rename="vol", type=int, report=True),
    ]

    def process(self, df):          # optional extra cleaning
        return df[df["vol"] != 0].copy()
```

`Column` options: `rename=`, `type=`, `keep=False` (read but drop),
`report=True` (print the column total before and after each step). Call
`self.report(df, "message")` inside `process` to log row counts as you filter.

Raw CSVs are read as **text** and cast to the declared types. A value that cannot be
cast raises an error naming the column, so bad data fails early.

## `model.py`: changing the flows

Model code follows one pattern, over and over:

```python
df = supplychain.get("flows")             # 1. take a copy
df = df[df["asset.level"] == 2]           # 2. pick the rows this rule applies to
df["status"] = "TO LP"                    # 3. compute new values
supplychain.update(df, ["status"])        # 4. write back only those columns
```

### `get(name, subset=None, prefix="")`

Returns a **copy** of a dataset (`"flows"`, `"asset"`, `"production"`, …) with linked
columns joined in. Every row carries a hidden `_id`, which `update` uses to match
rows. `prefix="storage_"` renames every column, which is useful when joining a
dataset to itself (see branch 3.1 in `model.py`).

### `update(df, columns, skip_conservation_check_for=None, allow_splitting=True)`

Writes `columns` from `df` back to the flows, matched on `_id`:

| What `df` contains | Effect |
|---|---|
| a subset of rows | only those flows change |
| several rows with the same `_id` | that flow is **split** into several flows |
| rows with `_id == -1` | **new** flows are added (as for domestic demand) |

Rows cannot be deleted with `update`; use `supplychain.replace(...)` for that.

### Conservation checks

Columns declared with `conserve=True` (here `vol` and `fob`) must have the same total
before and after every `update`. Splitting a 100 t flow into 60 t + 40 t is fine;
accidentally duplicating it into 100 t + 100 t raises an error. This catches the most
common supply-chain modelling bug: a merge on a non-unique key that silently multiplies
volume.

When you mean to change the total, as when adding domestic demand, say so:

```python
supplychain.update(df, df.columns, skip_conservation_check_for=["vol"])
```

When each flow should be labelled at most once, as in a decision-tree branch, pass
`allow_splitting=False`. An accidental duplicate then raises an error instead of
splitting the flow.

### Merges

The engine warns when `pd.merge` is called without `validate=`. Always state what you
expect (`"many_to_one"`, `"one_to_one"`, …) so that pandas raises an error if the data
breaks your assumption. `full_merge` (from `trase.tools.sei_pcs.pandas_utilities`)
also raises an error if any key is missing on either side.

## Linear programming

```python
from trase.tools.sei_pcs.pandas_lp import solve_transportation_problem

solution, _ = solve_transportation_problem(supply, demand, costs)
```

| Argument | pandas object |
|---|---|
| `supply` | Series indexed by source, value = available volume |
| `demand` | Series indexed by sink, value = required volume |
| `costs` | Series with a two-level index (source, sink), value = cost per unit |

The result is a Series indexed by (source, sink) holding the volume sent along each
pair. Total supply must be at least total demand, or there is no feasible solution.
`pandas_lp.py` contains other formulations (e.g. with an intermediate "via" step) for
more complex chains.

## Useful helpers

| Call | Does |
|---|---|
| `sc.flow_report_by_attribute("vol", ["branch"])` | totals and percentages by any columns |
| `sc.sankey("vol", ["municipality.name", "country"])` | Plotly Sankey diagram (needs `plotly`) |
| `sc.export_results(suffix="_test")` | writes `results_test.csv`, handy for comparing runs |
| `select_minimum(df, by, on)` | keep the lowest-`on` row per group (and per flow) |
| `TRASE_USE_TRACEMALLOC=1` | environment variable: print memory used by each step |
| `TRASE_LP_VERBOSE=1` | environment variable: show the LP solver's log |

## Starting a new model

1. Copy `trase/models/orvessa/candy/` to `trase/models/<country>/<commodity>/`.
2. Replace the files in `data/` and update the `Preprocessor` classes.
3. Edit `definition.py` to match your columns and links.
4. Run `sc.preparation()` and `sc.load()` until loading succeeds. Most errors at this
   stage are broken links or bad types, and the messages name the column.
5. Write `model.py` one rule at a time, checking `flow_report_by_attribute` after each.
6. Write checks in `quality_assurance.py` for anything that must always be true.

---

Previous: [3. Reading the results](3-reading-the-results.md) · Next: [5. Exercises](5-exercises.md)
