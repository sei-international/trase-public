"""Checks run after the model, by `SupplyChain.quality_assurance()`.

Each check raises an AssertionError with a short explanation if it fails.
"""

import numpy as np

from . import constants


def run(supplychain):
    df = supplychain.get("flows")
    df_production = supplychain.get("production")

    # every flow ends either SOLVED or UNKNOWN; "TO LP" would mean the LP missed it
    statuses = set(df["status"])
    assert statuses <= {"SOLVED", "UNKNOWN"}, f"unexpected statuses: {statuses}"

    # volumes and deforestation can never be negative
    assert (df["vol"] >= 0).all(), "negative volume"
    assert (df["deforestation"] >= 0).all(), "negative deforestation"

    # exports plus domestic demand add up to everything that was produced
    assert np.isclose(df["vol"].sum(), df_production["vol"].sum()), (
        "total volume of flows differs from total production"
    )

    # no municipality supplies more than it produced
    traced = df[df["municipality.code"] != constants.UNKNOWN_MUNICIPALITY_CODE]
    supplied = traced.groupby("municipality.code")["vol"].sum()
    produced = df_production.set_index("municipality.code")["vol"]
    excess = supplied.sub(produced, fill_value=0)
    over = excess[excess > 1e-6]
    assert over.empty, f"municipalities supply more than they produced:\n{over}"

    # every hectare of deforestation is attributed to some flow
    assert np.isclose(
        df["deforestation"].sum(), df_production["deforestation"].sum()
    ), "some deforestation was not attributed to any flow"

    # untraced exports carry deforestation too (unless the pool had none)
    untraced = df[df["status"] == "UNKNOWN"]
    if not untraced.empty and df_production["deforestation"].sum() > 0:
        assert untraced["deforestation"].sum() > 0, "untraced exports carry 0 ha"

    # domestic demand stays in the producing country
    domestic = df[df["branch"] == "DOMESTIC DEMAND"]
    assert (domestic["country"] == constants.COUNTRY).all(), "domestic flow exported"
