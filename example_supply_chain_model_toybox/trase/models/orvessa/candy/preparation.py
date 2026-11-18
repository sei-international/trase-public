"""Data preparation: turn the raw CSVs in data/ into the model's input files.

Each class below is a `Preprocessor`. When run it:

  1. copies `source_path` into `<year>/downloaded/`,
  2. keeps only the listed `Column`s, renaming and casting them as requested,
  3. calls `process(df)` (if defined) for any extra cleaning,
  4. writes the result to `<year>/prepared/<outname>`.

The `outname`s match the dataset names in definition.py, which is how the engine
finds them in `supplychain.load()`. `%YEAR%` in a path is replaced with the model
year.
"""

import os

import pandas as pd

from trase.tools.etl.processors import Column, Preprocessor
from trase.tools.sei_pcs.constants import CODEBASE_ROOT

from . import constants

DATA_DIRECTORY = os.path.join(CODEBASE_ROOT, "trase/models/orvessa/candy/data")


def preparation(context):
    """Entry point called by `SupplyChain.preparation()`."""
    Municipalities(context).run()
    Assets(context).run()
    Production(context).run()
    Distances(context).run()
    Flows(context).run()


class Municipalities(Preprocessor):
    source_path = os.path.join(DATA_DIRECTORY, "municipalities.csv")
    outname = "municipality.csv"
    columns = [
        Column("name"),
        Column("code", type=int),
        Column("trase_id"),
    ]

    def process(self, df):
        # Add a placeholder municipality so that flows we cannot trace still have a
        # valid link (see constants.UNKNOWN_MUNICIPALITY_CODE)
        unknown = pd.DataFrame(
            [
                {
                    "name": "UNKNOWN",
                    "code": constants.UNKNOWN_MUNICIPALITY_CODE,
                    "trase_id": "OV-UNKNOWN",
                }
            ]
        )
        return pd.concat([df, unknown], ignore_index=True)


class Assets(Preprocessor):
    source_path = os.path.join(DATA_DIRECTORY, "assets.csv")
    outname = "asset.csv"
    columns = [
        Column("identifier"),
        Column("name"),
        Column("municipality"),
        Column("level"),
        Column("company"),
    ]

    def process(self, df):
        # Add a placeholder asset for flows that have no exporter, such as domestic
        # consumption (see constants.UNKNOWN_ASSET_IDENTIFIER)
        unknown = pd.DataFrame(
            [
                {
                    "identifier": str(constants.UNKNOWN_ASSET_IDENTIFIER),
                    "name": "UNKNOWN",
                    "municipality": str(constants.UNKNOWN_MUNICIPALITY_CODE),
                    "level": "0",
                    "company": "",
                }
            ]
        )
        return pd.concat([df, unknown], ignore_index=True)


class Production(Preprocessor):
    source_path = os.path.join(DATA_DIRECTORY, "production_%YEAR%.csv")
    outname = "production.csv"
    columns = [
        Column("municipality"),
        # report=True prints the column total before and after each step, which makes
        # it easy to see how much volume a cleaning step removed
        Column("production_tonnes", rename="vol", type=int, report=True),
        Column("deforestation_ha", rename="deforestation", type=float, report=True),
    ]

    def process(self, df):
        # Municipalities that produced nothing cannot be a source of any flow. If one
        # still reports deforestation, dropping it would lose that deforestation
        # silently, so stop instead.
        no_production = df["vol"] == 0
        orphaned = df[no_production & (df["deforestation"] > 0)]
        if not orphaned.empty:
            raise ValueError(f"Deforestation without production:\n{orphaned}")
        df = df[~no_production].copy()
        self.report(df, "Drop zero volume")
        return df


class Distances(Preprocessor):
    source_path = os.path.join(DATA_DIRECTORY, "distances.csv")
    outname = "cost.csv"
    delimiter = ","
    columns = [
        Column("origin", type=int),
        Column("destination", type=int),
        Column("distance_km", rename="cost", type=int),
    ]


class Flows(Preprocessor):
    source_path = os.path.join(DATA_DIRECTORY, "customs_%YEAR%.csv")
    outname = "flows.csv"
    columns = [
        Column("hs6"),
        Column("exporter", rename="asset"),
        # The customs data records a municipality, but it is the exporter's address,
        # not the place of production, so we drop it: the model works that out
        Column("municipality", keep=False),
        Column("volume_tonnes", rename="vol", type=float),
        Column("fob_usd", rename="fob", type=float),
        Column("country"),
        Column("port"),
        Column("importer"),
    ]
