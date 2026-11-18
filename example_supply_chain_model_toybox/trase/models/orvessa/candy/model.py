"""The Orvessa candy supply-chain model.

Goal: for every customs declaration (an export flow), find the municipality where
the candyflower was produced, then attribute that municipality's deforestation to
the flow.

The model runs in four steps:

  1. decision_tree          - use what we know about the exporting asset to pick a
                              "storage" municipality: the hub the exporter sources from.
  2. linear_programming     - for flows with a hub, allocate production municipalities
                              to hubs, minimising total distance travelled.
  3. append_domestic_demand - production not taken by traced exports (the "unclaimed
                              pool") supplied the untraced exports and the domestic
                              market; add domestic flows from each municipality's
                              unclaimed production.
  4. embed_deforestation    - give every flow deforestation in proportion to its volume:
                              traced flows at their municipality's rate, untraced flows
                              at the average rate of the unclaimed pool.

After step 4 every municipality's production, and every hectare of deforestation, is
accounted for exactly once.

Working with the engine:
  * `supplychain.get("flows")` returns a *copy* of the flows as a DataFrame, with
    linked columns joined in (e.g. "asset.level", "asset.municipality.name").
  * `supplychain.update(df, columns)` writes the given columns back, matching rows
    by their hidden "_id". If `df` has several rows with the same "_id" the original
    flow is split into several flows; pass `allow_splitting=False` where that would
    be a bug. Conserved columns (vol, fob) are checked so that nothing is created or
    lost by mistake.
"""

import numpy as np
import pandas as pd

from trase.tools.sei_pcs.constants import ID
from trase.tools.sei_pcs.pandas_lp import solve_transportation_problem
from trase.tools.sei_pcs.pandas_utilities import select_minimum

from . import constants

# Asset levels, as recorded in data/assets.csv
FARM = 1
SILO = 2
FACTORY = 3


def run(supplychain):
    """Entry point called by `SupplyChain.run()`."""
    decision_tree(supplychain)
    linear_programming(supplychain)
    append_domestic_demand(supplychain)
    embed_deforestation(supplychain)


# ---------------------------------------------------------------------------------------
# Step 1: decision tree
# ---------------------------------------------------------------------------------------
def decision_tree(supplychain):
    """Assign each flow a branch, a status and (where possible) a storage hub.

    Flows that match a branch get status "TO LP" and a storage municipality.
    Flows that match no branch (e.g. exported by an office, level 5) keep the
    defaults from definition.py: branch "5 - Unknown", status "UNKNOWN".
    """
    # Copy the exporting asset's company and level onto every flow, for the results
    df = supplychain.get("flows")
    df["level"] = df["asset.level"]
    df["company"] = df["asset.company"]
    supplychain.update(df, ["level", "company"])

    # Branch 1: exported directly by a farm.
    # The farm's municipality is where the candyflower was collected.
    df = supplychain.get("flows")
    df = df[df["asset.level"] == FARM]
    df["branch"] = "1 - Asset linked to production"
    df["status"] = "TO LP"
    df["storage.name"] = df["asset.municipality.name"]
    supplychain.update(df, ["branch", "status", "storage.name"], allow_splitting=False)

    # Branch 2: exported by a storage silo.
    # The silo acts as a logistics hub collecting from nearby farms.
    df = supplychain.get("flows")
    df = df[df["asset.level"] == SILO]
    df["branch"] = "2 - Candy storage is logistic Hub"
    df["status"] = "TO LP"
    df["storage.name"] = df["asset.municipality.name"]
    supplychain.update(df, ["branch", "status", "storage.name"], allow_splitting=False)

    # Branch 3: exported by a factory.
    # Factories are often far from farms, so we assume the factory is supplied by
    # the *same company's* nearest storage silo, and use that silo as the hub.
    df = supplychain.get("flows")
    df = df[df["asset.level"] == FACTORY]

    # all silos, with columns prefixed "storage_" to keep them apart from the flow's
    df_assets = supplychain.get("asset", prefix="storage_")
    df_silos = df_assets[df_assets["storage_level"] == SILO]

    # pair each flow with every silo owned by the exporting company. Flows from a
    # company that owns no silos drop out here and stay UNKNOWN.
    df = pd.merge(
        df,
        df_silos,
        left_on="asset.company",
        right_on="storage_company",
        validate="many_to_many",  # a company can export many flows and own many silos
    )

    # add the distance from the factory to each candidate silo...
    df_costs = supplychain.get("cost")
    df = pd.merge(
        left=df,
        right=df_costs,
        left_on=["asset.municipality.code", "storage_municipality.code"],
        right_on=["origin.code", "destination.code"],
        how="left",
        validate="many_to_one",  # one distance per pair of municipalities
    )
    # ...and keep the closest silo for each flow (select_minimum groups by flow _id too)
    df = select_minimum(df, by=["asset.municipality.code"], on="cost")

    df["branch"] = "3.1 - Link to level 3 asset in known municipality"
    df["status"] = "TO LP"
    df["storage.name"] = df["storage_municipality.name"]
    supplychain.update(df, ["branch", "status", "storage.name"], allow_splitting=False)


# ---------------------------------------------------------------------------------------
# Step 2: linear programming
# ---------------------------------------------------------------------------------------
def linear_programming(supplychain):
    """Link storage hubs to production municipalities.

    This is a classic transportation problem:
      * sources = municipalities, supplying their production volume
      * sinks   = storage hubs, demanding the volume exported through them
      * cost    = distance between municipality and hub

    The solver finds the allocation that meets every hub's demand at minimum total
    distance. Each "TO LP" flow is then split across the municipalities supplying its
    hub, in proportion to how much each one supplied.
    """
    # sources: production volume per municipality
    sources = supplychain.get("production")
    sources = sources[sources["vol"] > 0]
    sources = sources.set_index("municipality.code")["vol"]

    # sinks: exported volume per storage hub
    df = supplychain.get("flows")
    df = df[df["status"] == "TO LP"]
    sinks = df.groupby("storage.code")["vol"].sum()

    # costs: distance between each pair of municipalities
    costs = supplychain.get("cost")
    costs = costs.set_index(["origin.code", "destination.code"])["cost"]

    # solve; the result is the volume sent along each (municipality, hub) pair
    solution, _ = solve_transportation_problem(sources, sinks, costs)
    solution = solution[solution > 1e-6]  # drop numerically-zero allocations
    solution = solution.reset_index()

    # turn volumes into the share of each hub's demand met by each municipality
    solution = pd.merge(
        solution,
        sinks,
        left_on="storage.code",
        right_index=True,
        suffixes=("_solved", "_demand"),
        validate="many_to_one",
    )
    solution["proportion"] = solution["vol_solved"] / solution["vol_demand"]
    solution = solution[["municipality.code", "storage.code", "proportion"]]
    solution = solution.rename(
        columns={"municipality.code": "source_code", "storage.code": "sink_code"}
    )

    # look up the names of the source municipalities
    df_municipality = supplychain.get("municipality", prefix="source_")
    solution = pd.merge(
        solution, df_municipality, on="source_code", validate="many_to_one"
    )

    # split each flow across its hub's sources. One flow can match several sources,
    # which is why this merge is many-to-many and why vol and fob are scaled.
    df = pd.merge(
        df,
        solution,
        left_on="storage.code",
        right_on="sink_code",
        validate="many_to_many",
    )
    df["vol"] *= df["proportion"]
    df["fob"] *= df["proportion"]
    df["status"] = "SOLVED"
    df["municipality.name"] = df.pop("source_name")

    supplychain.update(df, ["vol", "fob", "status", "municipality.name"])


# ---------------------------------------------------------------------------------------
# Shared by steps 3 and 4
# ---------------------------------------------------------------------------------------
DOMESTIC = "DOMESTIC DEMAND"


def unclaimed_production(supplychain) -> pd.Series:
    """Production in each municipality NOT used by traced exports, in tonnes.

    Traced exports are the SOLVED flows from the LP. Whatever they did not use is the
    "unclaimed pool": the only place the untraced exports and the domestic market
    can have got their candyflower from.

    Returns a Series indexed by municipality code. Every producing municipality is
    included, with 0 where the LP used all of its production.
    """
    production = supplychain.get("production").set_index("municipality.code")["vol"]

    flows = supplychain.get("flows")
    traced = flows[(flows["status"] == "SOLVED") & (flows["branch"] != DOMESTIC)]
    claimed = traced.groupby("municipality.code")["vol"].sum()

    unclaimed = production.sub(claimed, fill_value=0)
    # the LP never uses more than a municipality produced, but floating-point
    # arithmetic can leave tiny negative remainders such as -1e-12
    if (unclaimed < -1e-6).any():
        raise ValueError(
            f"Traced exports exceed production:\n{unclaimed[unclaimed < 0]}"
        )
    return unclaimed.clip(lower=0).reindex(production.index, fill_value=0)


# ---------------------------------------------------------------------------------------
# Step 3: domestic demand
# ---------------------------------------------------------------------------------------
def append_domestic_demand(supplychain):
    """Add flows for production that was consumed in Orvessa rather than exported.

    Without these flows the export flows would absorb all of a municipality's
    deforestation in step 4, overstating the impact of exports.

    Domestic demand is everything not exported. It can only have come from the
    unclaimed pool, and we assume it came from each municipality in proportion to
    that municipality's unclaimed production. The untraced exports take the rest of
    the pool, in the same proportions (see embed_deforestation).
    """
    unclaimed = unclaimed_production(supplychain)

    total_production = supplychain.get("production")["vol"].sum()
    total_export = supplychain.get("flows")["vol"].sum()
    domestic_total = total_production - total_export
    if domestic_total < 0 and not np.isclose(domestic_total, 0):
        raise ValueError("More export than production")
    if np.isclose(domestic_total, 0):
        return  # everything was exported; nothing to add

    # each municipality's share of the unclaimed pool. Municipalities the LP used up
    # have a share of 0 and supply no domestic demand.
    share = unclaimed / unclaimed.sum()
    share = share[share > 0]

    df_domestic = pd.DataFrame(
        {"municipality.code": share.index, "vol": domestic_total * share.values}
    )
    df_municipality = supplychain.get(
        "municipality", subset=["code", "name"], ids=False
    )
    df_domestic = pd.merge(
        df_domestic,
        df_municipality.rename(columns={"code": "municipality.code"}),
        on="municipality.code",
        validate="one_to_one",
    )
    df_domestic = df_domestic.drop(columns=["municipality.code"]).rename(
        columns={"name": "municipality.name"}
    )

    # fill in the remaining flow columns
    df_domestic[ID] = -1  # an _id of -1 tells update() to add these as new flows
    df_domestic["origin"] = constants.COUNTRY
    df_domestic["year"] = supplychain.context.year
    df_domestic["hs6"] = "000000"  # no product code: never crosses a border
    df_domestic["status"] = "SOLVED"
    df_domestic["branch"] = DOMESTIC
    df_domestic["fob"] = 0.0
    df_domestic["port"] = "NONE"
    df_domestic["asset.identifier"] = constants.UNKNOWN_ASSET_IDENTIFIER
    df_domestic["company"] = "NONE"
    df_domestic["country"] = constants.COUNTRY
    df_domestic["importer"] = "NONE"
    df_domestic["storage.name"] = df_domestic["municipality.name"]
    df_domestic["level"] = 0
    df_domestic["deforestation"] = 0.0  # filled in by embed_deforestation

    # vol is conserved, so tell the engine we are knowingly adding volume
    supplychain.update(
        df_domestic, df_domestic.columns, skip_conservation_check_for=["vol"]
    )


# ---------------------------------------------------------------------------------------
# Step 4: deforestation
# ---------------------------------------------------------------------------------------
def embed_deforestation(supplychain):
    """Give every flow its share of deforestation, in proportion to its volume.

    Each municipality's deforestation intensity is its deforestation divided by its
    production (ha per tonne).

      * Flows with a known municipality (traced exports and domestic demand) get
        volume x that municipality's intensity.
      * Untraced exports (municipality UNKNOWN) came from the unclaimed pool, so they
        get volume x the pool's average intensity, weighted by how much each
        municipality has unclaimed. They keep municipality UNKNOWN: we still don't
        know which municipality any one of them came from.

    Because traced flows + domestic demand + untraced exports together use up each
    municipality's production exactly, every hectare is attributed exactly once.
    """
    production = supplychain.get("production").set_index("municipality.code")
    intensity = production["deforestation"] / production["vol"]  # ha per tonne

    # average intensity of the unclaimed pool, weighted by unclaimed volume
    unclaimed = unclaimed_production(supplychain)
    if unclaimed.sum() > 0:
        pool_intensity = (unclaimed * intensity).sum() / unclaimed.sum()
    else:
        pool_intensity = 0.0  # nothing unclaimed, so there can be no untraced exports

    df = supplychain.get("flows")
    traced = df["municipality.code"] != constants.UNKNOWN_MUNICIPALITY_CODE
    df["deforestation"] = np.where(
        traced,
        df["vol"] * df["municipality.code"].map(intensity),
        df["vol"] * pool_intensity,
    )
    if df["deforestation"].isna().any():
        raise ValueError("A flow is linked to a municipality with no production data")

    supplychain.update(df, ["deforestation"])
