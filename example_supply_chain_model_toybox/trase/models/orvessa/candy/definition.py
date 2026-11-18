"""Definition of the Orvessa candy supply-chain model.

This file *declares* the shape of the model; it contains no logic. The SEI-PCS
engine reads it to know:

  * which prepared input files to load (`datasets`, `constraints`, `flows`),
  * which columns they have, their types and how they join to each other (`link=`),
  * which columns must be conserved while the model splits flows (`conserve=True`),
  * how to write the final results file (`flows_export`).

Helpers:
  c(name, type, link=..., key=..., value=..., conserve=...)  -> an input column
  e(output_name, input_column)                               -> an output column

A link such as `link="municipality.code"` means "this column is a foreign key to the
`code` column of the `municipality` dataset". Once loaded you can read linked values
with dotted names, for example `supplychain.get("flows")["asset.municipality.name"]`.
"""

# fmt: off
from trase.tools.sei_pcs.definition import Dataset, c, e
from trase.tools.sei_pcs.validation import Code

description = "Orvessa Candy Supply Chain Model"
version = "1.0.0"
commodity_equivalence_group_name = "CANDY"
years = [2017]
country = "orvessa"
commodity = "candy"

# ---------------------------------------------------------------------------------------
# Reference datasets: lookup tables that other datasets link to
# ---------------------------------------------------------------------------------------
datasets = {
    "municipality": Dataset([
        c("name"),
        c("code", int),
        c("trase_id"),  # stable public identifier, e.g. "OV-101"
    ]),
    "asset": Dataset([
        c("name"),
        c("identifier", int),
        c("municipality", link="municipality.code"),
        c("level", int),  # 1 farm, 2 silo, 3 factory, 5 other (e.g. office)
        c("company"),
    ]),
}

# ---------------------------------------------------------------------------------------
# Constraints: data that limits where flows can come from
# ---------------------------------------------------------------------------------------
constraints = {
    # how much each municipality produced, and the deforestation attributed to it
    "production": Dataset([
        c("municipality", link="municipality.name", key=True),
        c("vol", float),            # tonnes of candyflower
        c("deforestation", float),  # hectares
    ]),
    # distance between every pair of municipalities: the "cost" the LP minimises
    "cost": Dataset([
        c("origin", link="municipality.code", key=True),
        c("destination", link="municipality.code", key=True),
        c("cost", int),
    ]),
}

# ---------------------------------------------------------------------------------------
# Flows: one row per customs declaration. The model fills in the columns that
# have a default `value=`.
# ---------------------------------------------------------------------------------------
flows = [
    # columns read from the customs data
    c("hs6", validate=Code(6)),
    c("vol", float, conserve=True),  # total volume must not change when flows split
    c("fob", float, conserve=True),  # likewise for value
    c("asset", link="asset.identifier"),  # last known asset before export
    c("country"),
    c("port"),
    c("importer"),

    # columns added with defaults and filled in by model.py
    c("origin", value="ORVESSA"),
    c("year", int, value=2017),
    c("branch", value="5 - Unknown"),    # which decision-tree branch handled the flow
    c("status", value="UNKNOWN"),        # UNKNOWN -> TO LP -> SOLVED
    c("company", value=""),
    c("level", int, value=0),
    c("storage", link="municipality.name", value="UNKNOWN"),       # sourcing hub
    c("municipality", link="municipality.name", value="UNKNOWN"),  # place of production
    c("deforestation", float, value=0.0),
]

# ---------------------------------------------------------------------------------------
# Results file: the columns, in order, written by `supplychain.export_results()`
# ---------------------------------------------------------------------------------------
flows_export = [
    # The flow path, from production to consumption
    e("COUNTRY_OF_ORIGIN", "origin"),
    # ↓
    e("MUNICIPALITY_TRASE_ID_PROD", "municipality.trase_id"),
    # ↓
    e("PORT_OF_EXPORT", "port"),
    # ↓
    e("EXPORTER", "asset.name"),
    e("EXPORTER_TAX_ID", "asset.identifier"),
    # ↓
    e("IMPORTER", "importer"),
    e("COMPANY", "company"),
    # ↓
    e("COUNTRY_OF_DESTINATION", "country"),

    # Standard attributes
    e("VOLUME_RAW", "vol"),
    e("FOB", "fob"),
    e("HS6", "hs6"),
    e("YEAR", "year"),

    # Attributes that explain how each flow was mapped
    e("LEVEL", "level"),
    e("STORAGE", "storage.code"),
    e("BRANCH", "branch"),
    e("TERRITORIAL_DEFORESTATION", "deforestation"),
    e("STATUS", "status"),
]
