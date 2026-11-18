"""
Pandas-friendly wrapper functions for common linear programming problems that we
encounter in SEI-PCS.
"""

import os
from functools import partial, reduce
from logging import getLogger
from textwrap import indent
from unittest import mock

import pandas as pd
from pulp import (
    GLPK_CMD,
    PULP_CBC_CMD,
    LpMinimize,
    LpProblem,
    LpStatus,
    LpStatusOptimal,
    LpVariable,
    lpSum,
)
from slugify import slugify

from trase.tools.etl.utilities import consolidate
from trase.tools.sei_pcs.pandas_utilities import pretty_summarise, stitch_dataframes
from trase.tools.utilities.messages import print_message

LOGGER = getLogger(__name__)


def _validate_objects_are_pandas_series(*args):
    if any(not isinstance(series, pd.Series) for series in args):
        raise ValueError("Expected pd.Series objects")


def _validate_not_multi_index(*args):
    def _is_multi_index(index: pd.Index):
        return isinstance(index, pd.MultiIndex) or index.nlevels > 1

    if any(_is_multi_index(obj.index) for obj in args):
        raise ValueError("Expected single-level indexes")


def _validate_index_has_two_levels(*args):
    if any(obj.index.nlevels != 2 for obj in args):
        raise ValueError("Expected the index to have two levels")


def _default_solver():
    """The CBC solver bundled with PuLP.

    Its log is hidden unless the environment variable TRASE_LP_VERBOSE=1 is set.
    """
    return PULP_CBC_CMD(msg=os.environ.get("TRASE_LP_VERBOSE", "") == "1")


def _rename_series(series, name, index_name):
    return pd.Series(
        series.values,
        index=series.index.rename(index_name),
        dtype=series.dtype,
        name=name,
        copy=False,
    )


def solve_transportation_problem(
    supply: pd.Series,
    demand: pd.Series,
    costs: pd.Series,
    solver=None,
    on_missing: str = "raise",
    on_lp_error: str = "raise",
    allow_deviation=False,
    eq_constraints=None,
    geq_constraints=None,
    leq_constraints=None,
    commodity_ratios=None,
    solve_kwargs=None,
):
    warn_if_supply_sheds_demand_exceeds_supply(supply, demand, costs)

    if allow_deviation:
        try:
            return _solve_transportation_problem(
                supply=supply,
                demand=demand,
                costs=costs,
                solver=solver,
                on_missing=on_missing,
                on_lp_error=on_lp_error,
                allow_deviation=False,
                eq_constraints=eq_constraints,
                geq_constraints=geq_constraints,
                leq_constraints=leq_constraints,
                commodity_ratios=commodity_ratios,
                solve_kwargs=solve_kwargs,
            )
        except (RuntimeError, ValueError):
            return _solve_transportation_problem(
                supply=supply,
                demand=demand,
                costs=costs,
                solver=solver,
                on_missing=on_missing,
                on_lp_error=on_lp_error,
                allow_deviation=True,
                eq_constraints=eq_constraints,
                geq_constraints=geq_constraints,
                leq_constraints=leq_constraints,
                commodity_ratios=commodity_ratios,
                solve_kwargs=solve_kwargs,
            )
    else:
        return _solve_transportation_problem(
            supply=supply,
            demand=demand,
            costs=costs,
            solver=solver,
            on_missing=on_missing,
            on_lp_error=on_lp_error,
            allow_deviation=allow_deviation,
            eq_constraints=eq_constraints,
            geq_constraints=geq_constraints,
            leq_constraints=leq_constraints,
            commodity_ratios=commodity_ratios,
            solve_kwargs=solve_kwargs,
        )


def _solve_transportation_problem(
    supply: pd.Series,
    demand: pd.Series,
    costs: pd.Series,
    solver=None,
    on_missing: str = "raise",
    on_lp_error: str = "raise",
    allow_deviation=False,
    eq_constraints=None,
    geq_constraints=None,
    leq_constraints=None,
    commodity_ratios=None,
    solve_kwargs=None,
) -> pd.Series:
    """Solve the transportation problem using linear programming.

    Suppose a country has M farms ("sources") and N ports ("sinks"). Commodities are
    transported from the farms to the ports. Each farm has a capacity to supply, and
    each port has a demand quantity. We are given the transportation costs between
    every pair of farms and ports, and these costs are assumed to be linear to the
    quantity of commodity.

    The problem is to meet the demand at each sink at minimum cost without exhausting
    the supply at any source.

    If a cost is missing for any (source, sink) pair then it is assumed that delivery
    between that pair is not possible. If a supply capacity is missing for any source
    then no constraint will be applied at that source.

    It is possible to construct a problem where it is impossible to satisfy one or more
    sinks. This happens when there are no reachable sources with a defined capacity.
    That is to say, there are either no cost entries for a sink, or there are cost
    entries but there are no supply constraints for any of the sources. In this scenario
    the function will, by default, raise an error. However you can control the behaviour
    using the ``on_missing`` argument.

    TODO: analyse whether the problem has multiple optimal solutions

    Args:
        supply: a ``pd.Series`` of supply capacities, one row per source
        demand: a ``pd.Series`` of demand quantities, one row per sink
        costs: a ``pd.Series`` of costs with a multi-index of (source, sink) pairs
        on_missing: what action when it is impossible to satisfy one or more sinks.
            Should be one of "ignore" (exclude from problem and do nothing), "warn"
            (print warning), or "raise" (raise exception)
        on_lp_error: what action to take if the LP status is not optimal. Should be one
            of "ignore" (exclude from problem and do nothing), "warn" (print warning),
            or "raise" (raise exception)

    Raises:
        ValueError: if on_missing is "raise" and it is impossible to satisfy one or more
            sinks

    Returns:
        A ``pd.Series`` of quantities with a multi-index of (source, sink) pairs
    """

    if commodity_ratios == {}:
        commodity_ratios = None

    solver = solver or _default_solver()

    _validate_objects_are_pandas_series(supply, demand, costs)
    _validate_not_multi_index(supply)
    _validate_index_has_two_levels(costs)
    if commodity_ratios is not None:
        _validate_index_has_two_levels(demand)

    if supply.sum() < demand.sum() and not allow_deviation:
        print_message(
            f"Warning: supply ({supply.sum()}) is insufficient to meet demand ({demand.sum()}), the solver might fail",
            level="warn",
        )

    # save series names and index names
    supply_name, supply_index_name = supply.name, supply.index.name
    demand_name, demand_index_names = demand.name, demand.index.names

    n_demand_index_levels = demand.index.nlevels

    if n_demand_index_levels == 1:
        # add a "dummy" commodity to make the reset of the code simpler
        index = pd.MultiIndex.from_tuples([(i, "COMMODITY") for i in demand.index])
        demand = pd.Series(demand.values, index, demand.dtype, demand_name, copy=False)

    # replace series names and index names. we construct new objects so that we are
    # sure we are not mutating the input objects
    supply = _rename_series(supply, "supply", index_name="source")
    demand = _rename_series(demand, "demand", index_name=["sink", "commodity"])
    costs = _rename_series(costs, "cost", index_name=["source", "sink"])

    df_demand_groups = costs.to_frame().reset_index().sort_values(by="sink")
    df_demand_groups["source_cost"] = tuple(
        zip(df_demand_groups["source"], df_demand_groups["cost"])
    )
    df_demand_groups = (
        df_demand_groups.groupby("sink")["source_cost"]
        .apply(tuple)
        .reset_index()
        .groupby("source_cost")["sink"]
        .apply(list)
        .reset_index()
        .reset_index()
        .rename(columns={"index": "demand_group", "sink": "sinks"}, errors="raise")
        .set_index("demand_group")
    )

    # do not group demand for sinks that have additional constraints
    sinks_with_additional_constraints = []

    if eq_constraints is not None:
        sinks_with_additional_constraints += sorted(
            set([sink for _, sink in eq_constraints.index])
        )
    if geq_constraints is not None:
        sinks_with_additional_constraints += sorted(
            set([sink for _, sink in geq_constraints.index])
        )
    if leq_constraints is not None:
        sinks_with_additional_constraints += sorted(
            set([sink for _, sink in leq_constraints.index])
        )

    sink_demand_group = {sink: str(sink) for sink in sinks_with_additional_constraints}
    for _, row in df_demand_groups.iterrows():
        # use first sink as group name for all sinks in group
        demand_group = str(row["sinks"][0])
        for sink in row["sinks"]:
            if sink not in sinks_with_additional_constraints:
                sink_demand_group[sink] = demand_group

    df_demand = demand.to_frame().reset_index()
    df_demand["sink_group"] = df_demand["sink"].apply(lambda x: sink_demand_group[x])
    df_demand = consolidate(df_demand, ["demand"])
    df_grouped_demand = (
        df_demand.groupby(["sink_group", "commodity"])["demand"]
        .apply("sum")
        .to_frame()
        .reset_index()
    )

    df_supply = supply.to_frame().reset_index()
    df_costs = costs.to_frame().reset_index()
    df_costs["sink_group"] = df_costs["sink"].apply(lambda x: sink_demand_group[x])
    costs = (
        df_costs[["source", "sink_group", "cost"]]
        .drop_duplicates()
        .set_index(["source", "sink_group"])["cost"]
    )

    # additional constraints
    if eq_constraints is not None and not eq_constraints.empty:
        ((_, source_eq), (_, sink)) = eq_constraints.index.to_frame().items()
        eq = pd.DataFrame(
            {
                "source": source_eq.values,
                "sink": sink.values,
                "value": eq_constraints.values,
            }
        )
        # replace sink by sink_group and combine values
        eq["sink_group"] = eq["sink"].apply(lambda x: sink_demand_group[x])
        eq = eq.groupby(["source", "sink_group"])["value"].apply("sum")

    if geq_constraints is not None and not geq_constraints.empty:
        ((_, source_geq), (_, sink)) = geq_constraints.index.to_frame().items()
        geq = pd.DataFrame(
            {
                "source": source_geq.values,
                "sink": sink.values,
                "lower_limit": geq_constraints.values,
            }
        )
        # replace sink by sink_group and combine values
        geq["sink_group"] = geq["sink"].apply(lambda x: sink_demand_group[x])
        geq = geq.groupby(["source", "sink_group"])["lower_limit"].apply("sum")

    if leq_constraints is not None and not leq_constraints.empty:
        ((_, source_leq), (_, sink)) = leq_constraints.index.to_frame().items()
        leq = pd.DataFrame(
            {
                "source": source_leq.values,
                "sink": sink.values,
                "upper_limit": leq_constraints.values,
            }
        )
        # replace sink by sink_group and combine values
        leq["sink_group"] = leq["sink"].apply(lambda x: sink_demand_group[x])
        leq = leq.groupby(["source", "sink_group"])["upper_limit"].apply("sum")

    # match sources and sinks with costs. These are inner joins: any (source, sink) pair
    # without supply/demand/cost will be dropped from the problem
    how = "inner" if on_missing == "ignore" else "left"
    df = pd.merge(
        df_grouped_demand, costs.reset_index(), on="sink_group", validate=None, how=how
    )
    df = pd.merge(
        df, supply.reset_index(), on="source", validate="many_to_one", how=how
    )
    if df.empty:
        raise ValueError("Problem is empty: this could be due to mismatched indexes")

    # detect cases where demand is impossible to supply: either because there are no
    # supply constraints or there are no costs (i.e. no routes to any sinks). Missing a
    # supply constraint isn't *necessarily* a problem, it's just an "inexhaustible"
    # source, which practicaly we don't encounter in SEI-PCS
    if on_missing != "ignore":
        infeasible = df.groupby("sink_group").apply(
            lambda df_: all(df_["supply"].isna() | df_["cost"].isna()),
            include_groups=False,
        )
        if any(infeasible):
            pretty = indent(pretty_summarise(infeasible[infeasible].index), "\t")
            message = f"Some sinks are impossible to satisfy:\n{pretty}"
            if on_missing == "warn":
                LOGGER.warning(message)
            else:
                raise ValueError(message)

    # exclude infeasible sinks, missing costs, and missing demand from problem
    df = df[~df.isna().any(axis=1)]

    problem = LpProblem("TransportationProblem", LpMinimize)

    # make one LpVariable per (source, sink_group, commodity)
    variable_names = "v" + df.index.to_series().astype(str)
    df["variable"] = variable_names.apply(partial(LpVariable, lowBound=0))

    # production constraint: do not exceed supply
    for (source, supply), variables in df.groupby(["source", "supply"])["variable"]:
        problem += (lpSum(variables) <= supply, f"supply at {source}")

    if not allow_deviation:
        # demand constraint: meet demand exactly
        for (sink_group, commodity, demand), variables in df.groupby(
            ["sink_group", "commodity", "demand"]
        )["variable"]:
            problem += (
                lpSum(variables) == demand,
                f"{commodity} demand at {sink_group}",
            )
    else:
        # create variables for deviation
        df_deviation = df[["sink_group", "commodity", "demand"]].drop_duplicates()
        variable_names = "d_" + df_deviation.index.to_series().astype(str)
        df_deviation["variable"] = variable_names.apply(partial(LpVariable, lowBound=0))

        # add constraints to simulate absolute value of deviation
        for (
            (sink_group, commodity, demand_target),
            deviation_variables,
        ) in df_deviation.groupby(["sink_group", "commodity", "demand"])["variable"]:
            variables = df[
                (df["sink_group"] == sink_group) & (df["commodity"] == commodity)
            ]["variable"]
            problem += lpSum(deviation_variables) - demand_target <= lpSum(variables)
            problem += demand_target - lpSum(deviation_variables) <= lpSum(variables)

    # commodity ratios constraints
    if commodity_ratios is not None:
        # create variables for amount of untransformed commodity at sources
        variable_names = "u" + df_supply["source"].astype(str)
        df_supply["unprocessed_commodity_variable"] = variable_names.apply(
            partial(LpVariable, lowBound=0)
        )

        primary_commodity = [
            commodity for commodity, ratio in commodity_ratios.items() if ratio == 0
        ][0]
        derived_commodity_ratios = {
            commodity: ratio
            for commodity, ratio in commodity_ratios.items()
            if commodity != primary_commodity
        }

        # constraints on allocation of unprocessed commodity
        for (source, supply), variables in df[
            df["commodity"] == primary_commodity
        ].groupby(["source", "supply"])["variable"]:
            unprocessed_commodity_variable = df_supply.set_index("source").loc[
                source, "unprocessed_commodity_variable"
            ]
            problem += (
                lpSum(variables) <= unprocessed_commodity_variable,
                f"unprocessed commodity at {source}",
            )

        # constraints on allocation of processed commodities
        for commodity, ratio in derived_commodity_ratios.items():
            for (source, supply), variables in df[df["commodity"] == commodity].groupby(
                ["source", "supply"]
            )["variable"]:
                unprocessed_commodity_variable = df_supply.set_index("source").loc[
                    source, "unprocessed_commodity_variable"
                ]
                problem += (
                    lpSum(variables)
                    <= (supply - unprocessed_commodity_variable) * ratio,
                    f"processed commodity {commodity} at {source}",
                )

    # additional constraints
    if eq_constraints is not None and not eq_constraints.empty:
        df_eq = pd.merge(
            eq,
            df[["source", "sink_group", "variable"]],
            on=["source", "sink_group"],
            how="inner",
        )
        for (source, sink_group, value), variables in df_eq.groupby(
            ["source", "sink_group", "value"]
        )["variable"]:
            problem += lpSum(variables) == value

    if geq_constraints is not None and not geq_constraints.empty:
        df_geq = pd.merge(
            geq,
            df[["source", "sink_group", "variable"]],
            on=["source", "sink_group"],
            how="inner",
        )
        for (source, sink_group, lower_limit), variables in df_geq.groupby(
            ["source", "sink_group", "lower_limit"]
        )["variable"]:
            problem += lpSum(variables) >= lower_limit

    if leq_constraints is not None and not leq_constraints.empty:
        df_leq = pd.merge(
            leq,
            df[["source", "sink_group", "variable"]],
            on=["source", "sink_group"],
            how="inner",
        )
        for (source, sink_group, upper_limit), variables in df_leq.groupby(
            ["source", "sink_group", "upper_limit"]
        )["variable"]:
            problem += lpSum(variables) <= upper_limit

    if not allow_deviation:
        # objective function: the sum of each delivery multiplied by the cost
        problem += (lpSum(df["variable"] * df["cost"]), "total cost")
    else:
        problem += (
            lpSum(df["variable"] * df["cost"])
            + lpSum(df_deviation["variable"] * 1000000000),
            "total cost",
        )

    # solve
    status = problem.solve(solver, **(solve_kwargs or {}))
    if status != LpStatusOptimal:
        status = LpStatus.get(status, "Unknown")
        message = f"LP Status was not optimal: {status}"
        if on_lp_error == "ignore":
            pass
        elif on_lp_error == "warn":
            LOGGER.warning(message)
        else:  # "raise" or something unrecognised
            raise RuntimeError(message)

    # loop over the LpVariables and fetch the original (source, sink) objects
    df_allocation = pd.DataFrame(
        {"index": int(v.name[1:]), "quantity": v.varValue}
        for v in problem.variables()
        if v.name[0] == "v"
    )
    df_allocation = pd.merge(
        left=df[["source", "sink_group", "commodity"]],
        right=df_allocation,
        left_index=True,
        right_on="index",
        how="outer",
        indicator=True,
        validate=None,
    )
    if not all(df_allocation["_merge"] == "both"):
        raise ValueError
    df_allocation = df_allocation.drop(columns=["index", "_merge"])

    df_allocation = stitch_dataframes(
        df_demand.rename(columns={"demand": "quantity"}, errors="raise"),
        df_allocation,
        volume_column="quantity",
    )
    df_allocation = df_allocation[df_allocation["matched"]].drop(columns=["matched"])

    if n_demand_index_levels == 1:
        allocation = df_allocation.set_index(["source", "sink"])["quantity"]
    else:
        allocation = df_allocation.set_index(["source", "sink", "commodity"])[
            "quantity"
        ]

    df_allocated_supply = (
        df_allocation.groupby(["source"])["quantity"].apply("sum").to_frame()
    )
    df_allocated_supply = pd.merge(
        df_supply, df_allocated_supply, on="source", how="left", validate=None
    ).fillna(0)
    df_allocated_supply["leftover_supply"] = (
        df_allocated_supply["supply"] - df_allocated_supply["quantity"]
    )

    leftover_supply = df_allocated_supply.set_index("source")["leftover_supply"]

    # restore original series names and index names
    leftover_supply = _rename_series(leftover_supply, supply_name, supply_index_name)
    allocation = _rename_series(
        allocation, demand_name, index_name=[supply_index_name, *demand_index_names]
    )

    return allocation, leftover_supply


def _is_multi_index(index: pd.Index):
    return isinstance(index, pd.MultiIndex) or index.nlevels > 1


def solve_2_step_transportation_problem(
    supply: pd.Series,
    output: pd.Series,
    demand: pd.Series,
    costs_1: pd.Series,
    costs_2: pd.Series,
    output_deviation_cost_factor=None,
    solver=None,
    on_missing: str = "raise",
    eq_constraints_1=None,
    geq_constraints_1=None,
    leq_constraints_1=None,
    eq_constraints_2=None,
    geq_constraints_2=None,
    leq_constraints_2=None,
    commodity_ratios=None,
    solve_kwargs=None,
):
    """Solve 2-step transportation problem using linear programming.
    Suppose a country has M farms ("sources"), N processing facilities ("via") and P
    ports ("sinks"). Commodities are transported from the farms to the processing
    facilities, and to the ports. Each farm has a maximum quantity of commodity it can
    supply, each processing facility has a maximum quantity of commodity it can process,
    and each port has a demand quantity.

    We are given the transportation costs between every pair of farms and processing
    facilities, and between each pair of processing facilities and ports, and these
    costs are assumed to be linear to the quantity of commodity.

    The problem is to meet the demand at each sink at minimum cost without exhausting
    the supply at any source, and without exceeding the output at each via point.

    If a cost is missing for any (source, via) or (via, sink) pair then it is assumed
    that delivery is not possible. If a supply output is missing for any source it is
    assumed to be zero. If demand quantity is missing for any sink it is assumed to be
    zero.

    It is possible to construct a problem where it is impossible to satisfy one or more
    sinks and/or via points. This happens when there are no reachable sources with a defined capacity.
    That is to say, there are either no cost entries for any via-sink pair, or not cost entries
    for any source-via pair connected to the sink, or there are cost
    entries but there are no supply constraints for any of the sources. In this scenario
    the function will, by default, raise an error. However you can control the behaviour
    using the ``on_missing`` argument.

    Any number of additional constraints (equality, greater or equal, or lower or equal)
    can be specified for either steps of the path with the ..._constraints_... arguments.

    Args:
        supply: a ``pd.Series`` of supply capacities, one row per source
        demand: a ``pd.Series`` of demand quantities, one row per sink
        output: a ``pd.Series`` of capacities, one row per via point
        costs_1: a ``pd.Series`` of costs with a multi-index of (source, via) pairs
        costs_2: a ``pd.Series`` of costs with a multi-index of (via, sink) pairs
        output_deviation_cost_factor: when value is None, the output for all "via"
            points needs to be met exactly. When value is non-null, any quantity
            in excess or deficit compared with the output adds a cost to the
            objective function by multiplying the amount with the cost factor.
              One way to understand the meaning of the factor is the following:
            when the factor has value X, sourcing trough a via point V1 without
            available output is as costly as sourcing through another
            via point V2 with available output located "further" by X units
            of transportation cost.
              For instance, if transportation costs are in minutes, a cost factor
            of 120 means that it would be cheaper to source through any via
            point with available output located less than 2 hours further from
            the final destination than from a via point that has no available output.
        eq_constraints_1: a ``pd.Series`` of expected allocation between sources and via points.
        geq_constraints_1: a ``pd.Series`` of lower limit of allocation between sources and via points.
        leq_constraints_1: a ``pd.Series`` of upper limit of allocation between sources and via points.
        eq_constraints_2: a ``pd.Series`` of expected allocation between via points and sinks.
        geq_constraints_2: a ``pd.Series`` of lower limit of allocation between via points and sinks.
        leq_constraints_2: a ``pd.Series`` of upper limit of allocation between via points and sinks.

    Returns:
        allocation: a ``pd.Series`` of quantities with a multi-index of (source, via, sink) pairs
        leftover_supply: a ``pd.Series`` of unallocated supply, one row per source
        leftover_output: a ``pd.Series`` of unallocated output, one row per via point
    """

    if commodity_ratios == {}:
        commodity_ratios = None

    solver = solver or _default_solver()

    _validate_objects_are_pandas_series(supply, output, demand, costs_1, costs_2)
    _validate_not_multi_index(supply, output)
    _validate_index_has_two_levels(costs_1, costs_2)
    if commodity_ratios is not None:
        _validate_index_has_two_levels(demand)

    if supply.sum() < demand.sum():
        raise ValueError(
            f"Supply ({supply.sum()}) is insufficient to meet demand ({demand.sum()})"
        )

    # save series names and index names
    supply_name, supply_index_name = supply.name, supply.index.name
    demand_name, demand_index_names = demand.name, demand.index.names
    output_name, output_index_name = output.name, output.index.name

    n_demand_index_levels = demand.index.nlevels

    if n_demand_index_levels == 1:
        # add a "dummy" commodity to make the reset of the code simpler
        index = pd.MultiIndex.from_tuples([(i, "COMMODITY") for i in demand.index])
        demand = pd.Series(demand.values, index, demand.dtype, demand_name, copy=False)

    # replace series names and index names. we construct new objects so that we are
    # sure we are not mutating the input objects
    supply = _rename_series(supply, "supply", index_name="source")
    demand = _rename_series(demand, "demand", index_name=["sink", "commodity"])
    output = _rename_series(output, "output", index_name="via")
    costs_1 = _rename_series(costs_1, "cost_1", index_name=["source", "via"])
    costs_2 = _rename_series(costs_2, "cost_2", index_name=["via", "sink"])

    df_commodities = pd.DataFrame(
        columns=["commodity"], data=demand.reset_index()["commodity"].drop_duplicates()
    )

    df_demand_groups = costs_2.to_frame().reset_index().sort_values(by=["sink", "via"])
    df_demand_groups["via_cost"] = tuple(
        zip(df_demand_groups["via"], df_demand_groups["cost_2"])
    )
    df_demand_groups = (
        df_demand_groups.groupby("sink")["via_cost"]
        .apply(tuple)
        .reset_index()
        .groupby("via_cost")["sink"]
        .apply(list)
        .reset_index()
        .reset_index()
        .rename(columns={"index": "demand_group", "sink": "sinks"}, errors="raise")
        .set_index("demand_group")
    )

    # do not group demand for sinks that have additional constraints
    sinks_with_additional_constraints = []

    if eq_constraints_2 is not None:
        sinks_with_additional_constraints += sorted(
            set([sink for _, sink in eq_constraints_2.index])
        )
    if geq_constraints_2 is not None:
        sinks_with_additional_constraints += sorted(
            set([sink for _, sink in geq_constraints_2.index])
        )
    if leq_constraints_2 is not None:
        sinks_with_additional_constraints += sorted(
            set([sink for _, sink in leq_constraints_2.index])
        )

    sink_demand_group = {sink: str(sink) for sink in sinks_with_additional_constraints}
    for _, row in df_demand_groups.iterrows():
        # use first sink as group name for all sinks in group
        demand_group = str(row["sinks"][0])
        for sink in row["sinks"]:
            if sink not in sinks_with_additional_constraints:
                sink_demand_group[sink] = demand_group

    df_demand = demand.to_frame().reset_index()
    df_demand["sink_group"] = df_demand["sink"].apply(lambda x: sink_demand_group[x])
    df_demand = consolidate(df_demand, ["demand"])
    df_grouped_demand = (
        df_demand.groupby(["sink_group", "commodity"])["demand"]
        .apply("sum")
        .to_frame()
        .reset_index()
    )

    df_supply = supply.to_frame().reset_index()
    df_costs_1 = costs_1.to_frame().reset_index()
    df_output = output.to_frame().reset_index()
    df_costs_2 = costs_2.to_frame().reset_index()
    df_costs_2["sink_group"] = df_costs_2["sink"].apply(lambda x: sink_demand_group[x])
    costs_2 = (
        df_costs_2[["via", "sink_group", "cost_2"]]
        .drop_duplicates()
        .set_index(["via", "sink_group"])["cost_2"]
        .to_frame()  # TODO: check if can be simplified
        .reset_index()
    )

    # additional constraints
    if eq_constraints_1 is not None and not eq_constraints_1.empty:
        (
            (_, source_eq_1),
            (_, via_eq_1),
        ) = eq_constraints_1.index.to_frame().items()
        eq_1 = pd.DataFrame(
            {
                "source": source_eq_1.values,
                "via": via_eq_1.values,
                "value": eq_constraints_1.values,
            }
        )

    if geq_constraints_1 is not None and not geq_constraints_1.empty:
        (
            (_, source_geq_1),
            (_, via_geq_1),
        ) = geq_constraints_1.index.to_frame().items()
        geq_1 = pd.DataFrame(
            {
                "source": source_geq_1.values,
                "via": via_geq_1.values,
                "lower_limit": geq_constraints_1.values,
            }
        )

    if leq_constraints_1 is not None and not leq_constraints_1.empty:
        (
            (_, source_leq_1),
            (_, via_leq_1),
        ) = leq_constraints_1.index.to_frame().items()
        leq_1 = pd.DataFrame(
            {
                "source": source_leq_1.values,
                "via": via_leq_1.values,
                "upper_limit": leq_constraints_1.values,
            }
        )

    if eq_constraints_2 is not None and not eq_constraints_2.empty:
        ((_, via_eq_2), (_, sink_2)) = eq_constraints_2.index.to_frame().items()
        eq_2 = pd.DataFrame(
            {
                "via": via_eq_2.values,
                "sink": sink_2.values,
                "value": eq_constraints_2.values,
            }
        )
        # replace sink by sink_group and combine values
        eq_2["sink_group"] = eq_2["sink"].apply(lambda x: sink_demand_group[x])
        eq_2 = eq_2.groupby(["via", "sink_group"])["value"].apply("sum")

    if geq_constraints_2 is not None and not geq_constraints_2.empty:
        ((_, via_geq_2), (_, sink_2)) = geq_constraints_2.index.to_frame().items()
        geq_2 = pd.DataFrame(
            {
                "via": via_geq_2.values,
                "sink": sink_2.values,
                "lower_limit": geq_constraints_2.values,
            }
        )
        # replace sink by sink_group and combine values
        geq_2["sink_group"] = geq_2["sink"].apply(lambda x: sink_demand_group[x])
        geq_2 = geq_2.groupby(["via", "sink_group"])["lower_limit"].apply("sum")

    if leq_constraints_2 is not None and not leq_constraints_2.empty:
        ((_, via_leq_2), (_, sink_2)) = leq_constraints_2.index.to_frame().items()
        leq_2 = pd.DataFrame(
            {
                "via": via_leq_2.values,
                "sink": sink_2.values,
                "upper_limit": leq_constraints_2.values,
            }
        )
        # replace sink by sink_group and combine values
        leq_2["sink_group"] = leq_2["sink"].apply(lambda x: sink_demand_group[x])
        leq_2 = leq_2.groupby(["via", "sink_group"])["upper_limit"].apply("sum")

    # match sources and sinks through via points with costs. These are inner joins: any (source, sink) pair
    # without supply/demand/cost will be dropped from the problem
    how = "inner" if on_missing == "ignore" else "left"
    df_1 = pd.merge(df_supply, df_costs_1, on="source", how=how)
    df_1 = pd.merge(df_1, df_output, on="via", how=how)
    df_1["key"] = True
    df_commodities["key"] = True
    df_1 = pd.merge(df_1, df_commodities, on="key").drop(columns="key")

    df_2 = pd.merge(df_output, df_costs_2, on="via", how=how)
    df_2 = pd.merge(df_2, df_grouped_demand, on="sink_group", how=how)

    df_1 = pd.merge(df_2[["via"]].drop_duplicates(), df_1, on="via", how=how)
    df_2 = pd.merge(df_1[["via"]].drop_duplicates(), df_2, on="via", how=how)

    if df_1.empty or df_2.empty:
        raise ValueError("Problem is empty: this could be due to mismatched indexes")

    # detect cases where demand is impossible to supply: either because there are no
    # supply constraints or there are no costs (i.e. no routes to any sinks). Missing a
    # supply constraint isn't *necessarily* a problem, it's just an "inexhaustible"
    # source, which practicaly we don't encounter in SEI-PCS
    if on_missing != "ignore":
        infeasible = df_1.groupby("via").apply(
            lambda df_: all(df_["supply"].isna() | df_["cost_1"].isna()),
            include_groups=False,
        )
        if any(infeasible):
            pretty = indent(pretty_summarise(infeasible[infeasible].index), "\t")
            message = f"Some via points are impossible to satisfy:\n{pretty}"
            if on_missing == "warn":
                LOGGER.warning(message)
            else:
                raise ValueError(message)

        infeasible = df_2.groupby("sink_group").apply(
            lambda df_: all(df_["output"].isna() | df_["cost_2"].isna()),
            include_groups=False,
        )
        if any(infeasible):
            pretty = indent(pretty_summarise(infeasible[infeasible].index), "\t")
            message = f"Some via points are impossible to satisfy:\n{pretty}"
            if on_missing == "warn":
                LOGGER.warning(message)
            else:
                raise ValueError(message)

    # exclude infeasible sinks, missing costs, and missing demand from problem
    df_1 = df_1[~df_1.isna().any(axis=1)]
    df_2 = df_2[~df_2.isna().any(axis=1)]

    problem = LpProblem("TransportationProblem", LpMinimize)

    # make one LpVariable per (source, via, commodity)
    variable_names = "v1_" + df_1.index.to_series().astype(str)
    df_1["variable_1"] = variable_names.apply(partial(LpVariable, lowBound=0))

    # make one LpVariable per (via, sink, commodity)
    variable_names = "v2_" + df_2.index.to_series().astype(str)
    df_2["variable_2"] = variable_names.apply(partial(LpVariable, lowBound=0))

    # production constraint: do not exceed supply
    for (source, supply), variables_1 in df_1.groupby(["source", "supply"])[
        "variable_1"
    ]:
        problem += (lpSum(variables_1) <= supply, f"supply at {source}")

    # demand constraint: meet demand exactly
    for (sink_group, commodity, demand), variables_2 in df_2.groupby(
        ["sink_group", "commodity", "demand"]
    )["variable_2"]:
        problem += (lpSum(variables_2) == demand, f"{commodity} demand at {sink_group}")

    # output constraint: input and output identical for all via points
    for (via, commodity), variables_1 in df_1.groupby(["via", "commodity"])[
        "variable_1"
    ]:
        variables_2 = df_2[(df_2["via"] == via) & (df_2["commodity"] == commodity)][
            "variable_2"
        ]
        problem += (
            lpSum(variables_1) == lpSum(variables_2),
            f"{commodity} input output at {via}",
        )

    # commodity ratios constraints
    if commodity_ratios is not None:
        # create variables for amount of untransformed commodity at sources
        variable_names = "u" + df_supply["source"].astype(str)
        df_supply["unprocessed_commodity_variable"] = variable_names.apply(
            partial(LpVariable, lowBound=0)
        )

        primary_commodity = [
            commodity for commodity, ratio in commodity_ratios.items() if ratio == 0
        ][0]
        derived_commodity_ratios = {
            commodity: ratio
            for commodity, ratio in commodity_ratios.items()
            if commodity != primary_commodity
        }

        # constraints on allocation of unprocessed commodity
        for (source, supply), variables_1 in df_1[
            df_1["commodity"] == primary_commodity
        ].groupby(["source", "supply"])["variable_1"]:
            unprocessed_commodity_variable = df_supply.set_index("source").loc[
                source, "unprocessed_commodity_variable"
            ]
            problem += (
                lpSum(variables_1) <= unprocessed_commodity_variable,
                f"unprocessed commodity at {source}",
            )

        # constraints on allocation of processed commodities
        for commodity, ratio in derived_commodity_ratios.items():
            for (source, supply), variables_1 in df_1[
                df_1["commodity"] == commodity
            ].groupby(["source", "supply"])["variable_1"]:
                unprocessed_commodity_variable = df_supply.set_index("source").loc[
                    source, "unprocessed_commodity_variable"
                ]
                problem += (
                    lpSum(variables_1)
                    <= (supply - unprocessed_commodity_variable) * ratio,
                    f"processed commodity {commodity} at {source}",
                )

    # additional constraints
    if eq_constraints_1 is not None and not eq_constraints_1.empty:
        df_eq_1 = pd.merge(
            eq_1,
            df_1[["via", "sink_group", "variable_1"]],
            on=["via", "sink_group"],
            how="inner",
        )
        for (via, sink_group, value), variables in df_eq_1.groupby(
            ["via", "sink_group", "value"]
        )["variable_1"]:
            problem += lpSum(variables) == value

    if geq_constraints_1 is not None and not geq_constraints_1.empty:
        df_geq_1 = pd.merge(
            geq_1,
            df_1[["via", "sink_group", "variable_1"]],
            on=["via", "sink_group"],
            how="inner",
        )
        for (via, sink_group, lower_limit), variables in df_geq_1.groupby(
            ["via", "sink_group", "lower_limit"]
        )["variable_1"]:
            problem += lpSum(variables) >= lower_limit

    if leq_constraints_1 is not None and not leq_constraints_1.empty:
        df_leq_1 = pd.merge(
            leq_1,
            df_1[["via", "sink_group", "variable_1"]],
            on=["via", "sink_group"],
            how="inner",
        )
        for (via, sink_group, upper_limit), variables in df_leq_1.groupby(
            ["via", "sink_group", "upper_limit"]
        )["variable_1"]:
            problem += lpSum(variables) <= upper_limit

    if eq_constraints_2 is not None and not eq_constraints_2.empty:
        df_eq_2 = pd.merge(
            eq_2,
            df_2[["via", "sink_group", "variable_2"]],
            on=["via", "sink_group"],
            how="inner",
        )
        for (via, sink_group, value), variables in df_eq_2.groupby(
            ["via", "sink_group", "value"]
        )["variable_2"]:
            problem += lpSum(variables) == value

    if geq_constraints_2 is not None and not geq_constraints_2.empty:
        df_geq_2 = pd.merge(
            geq_2,
            df_2[["via", "sink_group", "variable_2"]],
            on=["via", "sink_group"],
            how="inner",
        )
        for (via, sink, lower_limit), variables in df_geq_2.groupby(
            ["via", "sink_group", "lower_limit"]
        )["variable_2"]:
            problem += lpSum(variables) >= lower_limit

    if leq_constraints_2 is not None and not leq_constraints_2.empty:
        df_leq_2 = pd.merge(
            leq_2,
            df_2[["via", "sink_group", "variable_2"]],
            on=["via", "sink_group"],
            how="inner",
        )
        for (via, sink, upper_limit), variables in df_leq_2.groupby(
            ["via", "sink_group", "upper_limit"]
        )["variable_2"]:
            problem += lpSum(variables) <= upper_limit

    if output_deviation_cost_factor is None:
        # processing constraint: do not exceed output
        for (via, output_target), variables in df_1.groupby(["via", "output"])[
            "variable_1"
        ]:
            problem += (lpSum(variables) == output_target, f"output at {via}")

        # objective function: the sum of each delivery multiplied by the cost
        problem += (
            lpSum(df_1["variable_1"] * df_1["cost_1"])
            + lpSum(df_2["variable_2"] * df_2["cost_2"]),
            "cost",
        )

    else:
        # create variables for deviation
        df_deviation = df_1[["via", "output"]].drop_duplicates()
        variable_names = "d_" + df_deviation.index.to_series().astype(str)
        df_deviation["variable"] = variable_names.apply(partial(LpVariable, lowBound=0))

        # add constraints to simulate absolute value of deviation
        for (via, output_target), deviation_variables in df_deviation.groupby(
            ["via", "output"]
        )["variable"]:
            variables_1 = df_1[df_1["via"] == via]["variable_1"]
            problem += lpSum(deviation_variables) - output_target <= lpSum(variables_1)
            problem += output_target - lpSum(deviation_variables) <= lpSum(variables_1)

        # objective function
        problem += (
            lpSum(df_1["variable_1"] * df_1["cost_1"])
            + lpSum(df_2["variable_2"] * df_2["cost_2"])
            + lpSum(df_deviation["variable"] * output_deviation_cost_factor),
            "cost",
        )

    # solve
    status = problem.solve(solver, **(solve_kwargs or {}))
    if status != LpStatusOptimal:
        raise RuntimeError(LpStatus.get(status, "Unknown"))

    # loop over the LpVariables and fetch the original (source, via, sink) objects
    df_allocation_1 = pd.DataFrame(
        {"index": int(v.name[3:]), "quantity": v.varValue}
        for v in problem.variables()
        if v.name[1] == "1"
    )

    df_allocation_1 = pd.merge(
        left=df_1[["source", "via", "commodity"]],
        right=df_allocation_1,
        left_index=True,
        right_on="index",
        how="outer",
        indicator=True,
    )
    if not all(df_allocation_1["_merge"] == "both"):
        raise RuntimeError("LP solution does not match the input rows")
    df_allocation_1 = df_allocation_1.drop(columns=["index", "_merge"])

    df_allocation_2 = pd.DataFrame(
        {"index": int(v.name[3:]), "quantity": v.varValue}
        for v in problem.variables()
        if v.name[1] == "2"
    )

    df_allocation_2 = pd.merge(
        left=df_2[["via", "sink_group", "commodity"]],
        right=df_allocation_2,
        left_index=True,
        right_on="index",
        how="outer",
        indicator=True,
    )
    if not all(df_allocation_2["_merge"] == "both"):
        raise RuntimeError("LP solution does not match the input rows")
    df_allocation_2 = df_allocation_2.drop(columns=["index", "_merge"])

    df_allocation = stitch_dataframes(
        df_allocation_1, df_allocation_2, volume_column="quantity"
    )
    df_allocation = df_allocation[df_allocation["matched"]].drop(columns=["matched"])

    df_allocation = stitch_dataframes(
        df_demand.rename(columns={"demand": "quantity"}, errors="raise"),
        df_allocation,
        volume_column="quantity",
    )
    df_allocation = df_allocation[df_allocation["matched"]].drop(columns=["matched"])

    if n_demand_index_levels == 1:
        allocation = df_allocation.set_index(["source", "via", "sink"])["quantity"]
    else:
        allocation = df_allocation.set_index(["source", "via", "sink", "commodity"])[
            "quantity"
        ]

    df_allocated_output = (
        df_allocation.groupby("via")["quantity"].apply("sum").to_frame()
    )
    df_allocated_output = pd.merge(
        df_output, df_allocated_output, how="left", on="via"
    ).fillna(0)
    df_allocated_output["leftover_output"] = (
        df_allocated_output["output"] - df_allocated_output["quantity"]
    )
    df_allocated_output["leftover_output"] = df_allocated_output[
        "leftover_output"
    ].mask(df_allocated_output["leftover_output"] < 0, 0)

    df_allocated_supply = (
        df_allocation.groupby(["source"])["quantity"].apply("sum").to_frame()
    )
    df_allocated_supply = pd.merge(
        df_supply, df_allocated_supply, on="source", how="left"
    ).fillna(0)
    df_allocated_supply["leftover_supply"] = (
        df_allocated_supply["supply"] - df_allocated_supply["quantity"]
    )

    leftover_supply = df_allocated_supply.set_index("source")["leftover_supply"]
    leftover_output = df_allocated_output.set_index("via")["leftover_output"]

    # restore original series names and index names
    leftover_supply = _rename_series(leftover_supply, supply_name, supply_index_name)
    leftover_output = _rename_series(leftover_output, output_name, output_index_name)
    allocation = _rename_series(
        allocation,
        demand_name,
        index_name=[supply_index_name] + [output_index_name] + demand_index_names,
    )

    return allocation, leftover_supply, leftover_output


class TraseGlpkCommand(GLPK_CMD):
    """This is Pulp's GLPK_CMD but with a trick to capture stdout

    Usually GLPK_CMD has two modes:

     1. `msg=True`, in which case glpk is run as a fork of the current Python process
     2. `msg=False`, in which case the output of glpl is sent to /dev/null

    The intention of 1. is that the stdout of glpk is sent to the user. However, we have
    an odd problem that is very specific to DeforestationFree where the output is simply
    lost.

    You can reproduce this problem by running the following code:

    ```python
    import os
    os.spawnvp(os.P_WAIT, "echo", ["echo", "hi"])
    ```

    If you run this locally you will see the output "hi". However if you run it in a
    Jupyter notebook on DeforestationFree you see nothing. I suspect that the output is
    being sent to the terminal rather than the notebook, perhaps the same problem as
    https://github.com/jupyterlab/jupyterlab/issues/9668. I hope that an upgrade or
    re-deployment of JupyterHub will resolve this issue.

    Until then I have resorted to this clever trick, which is to patch `os.devnull`
    with a filename and pass `msg=False`. The pulp code runs `open(os.devnull, "w")`
    which actually results it in opening the text file!

    To use this class do the following:

    ```python
    solver = TraseGlpkCommand()
    solve_transportation_problem(supply, demand, costs, solver=solver)
    ```
    """

    def __init__(self, logPath="glpk.log", msg=False, **kwargs):
        super().__init__(msg=msg, **kwargs)
        self.logPath = logPath

    def actualSolve(self, lp):
        path = os.path.abspath(self.logPath)
        with mock.patch("os.devnull", path):
            LOGGER.info(f"GLPK output will be written to {path}")
            return super().actualSolve(lp)


def make_variable_name(df, columns, truncate_after=20, check=True) -> pd.Series:
    """Make a Pulp variable name from a dataframe.

    The return value will be a `pd.Series` object where each row consists of the
    provided columns concatenated together. To ensure uniqueness we also prepend the
    index of the dataframe. Since the columns can contain abitrary strings, we slugify
    their contents and truncate them if they are too long.

    Example:

        >>> df = pd.DataFrame([
        ...     {"port": "ACRE", "company": "PIMEX"},
        ...     {"port": "AIOI", "company": "SODRU"},
        ...     {"port": "COGO", "company": "ABC SHIPPING"},
        ... ])
        >>> names = make_variable_name(df_2, ["port", "company"], truncate_after=10)
        >>> names
        0         0_acre_pimex
        1         1_aioi_sodru
        2    2_cogo_abc-shippi
        dtype: object
        >>> names.apply(pulp.LpVariable) # constructing PuLP variables using these names

    Args:
        df: dataframe containing the necessary data to construct the variable names
        columns: the columns of the dataframe that will be included in the name. All
            values will be cast to strings. Note that the index of the dataframe will
            also be included.
        truncate_after (int, optional): when to truncate values (default: 20 characters)
        check (bool, optional): optionally raise an error if the names are not unique
            (default: True)

    Returns:
        A `pd.Series` object containing strings
    """

    def sanitise(items):
        return items.astype(str).str.lower().apply(slugify).str.slice(0, truncate_after)

    ret = reduce(
        lambda series, column: series + "_" + sanitise(df[column]),
        columns,
        sanitise(pd.Series(df.index)),  # initial value
    )
    if check and not ret.is_unique:
        raise ValueError("Variable names have duplicated values")
    return ret


def warn_if_supply_sheds_demand_exceeds_supply(
    supply: pd.Series,
    demand: pd.Series,
    costs: pd.Series,
):
    """
    The total LP supply sometimes appears sufficient to meet the total demand,
    but the details of the available paths in the cost matrix make it impossible
    for some of the supply to reach the demand.
    When such issues occur, the LP just doesn't find a solution, but does not give
    any hint about what may be the issue.
    This function identifies supply sheds: groups of sources connected to the same group of sinks,
    and flags supply sheds for which there is excess demand.
    """
    n_demand_index_levels = demand.index.nlevels
    if n_demand_index_levels == 1:
        index = pd.MultiIndex.from_tuples([(i, "COMMODITY") for i in demand.index])
        demand = pd.Series(demand.values, index, demand.dtype, demand.name, copy=False)

    supply = _rename_series(supply, "supply", index_name="source")
    demand = _rename_series(demand, "demand", index_name=["sink", "commodity"])
    costs = _rename_series(costs, "cost", index_name=["source", "sink"])

    df_demand = demand.reset_index()
    df_demand = df_demand.drop(columns="COMMODITY", errors="ignore")
    demand = df_demand.set_index("sink")["demand"]

    df_costs = costs.reset_index()

    shed_sources = {}
    source_sheds = {}
    shed_sinks = {}
    sink_sheds = {}
    shed_counter = 0
    for _, row in df_costs.iterrows():
        source = row["source"]
        sink = row["sink"]
        source_shed = None
        sink_shed = None

        # source already assigned to shed
        if source in source_sheds:
            source_shed = source_sheds[source]

        # sink already assigned to shed
        if sink in sink_sheds:
            sink_shed = sink_sheds[sink]

        # only source assigned to shed: assing sink to same shed
        if source_shed is not None and sink_shed is None:
            sink_sheds[sink] = source_shed
            shed_sinks[source_shed].add(sink)

        # only sink assigned to shed: assing source to same shed
        if sink_shed is not None and source_shed is None:
            source_sheds[source] = sink_shed
            shed_sources[sink_shed].add(source)

        # neither source nor sink part of existing shed: create new shed
        if sink_shed is None and source_shed is None:
            shed_sources[shed_counter] = {source}
            shed_sinks[shed_counter] = {sink}
            source_sheds[source] = shed_counter
            sink_sheds[sink] = shed_counter
            shed_counter += 1

        # source and sink assigned to different sheds: merge sink shed into source shed
        if (
            source_shed is not None
            and sink_shed is not None
            and source_shed != sink_shed
        ):
            shed_sources[source_shed].update(shed_sources[sink_shed])
            del shed_sources[sink_shed]
            shed_sinks[source_shed].update(shed_sinks[sink_shed])
            del shed_sinks[sink_shed]
            source_sheds[source] = source_shed
            sink_sheds[sink] = source_shed

            # update shed for all sinks and sources linked to sink shed
            for sink in sink_sheds:
                if sink_sheds[sink] == sink_shed:
                    sink_sheds[sink] = source_shed
            for source in source_sheds:
                if source_sheds[source] == sink_shed:
                    source_sheds[source] = source_shed

    source_supply = supply.to_dict()
    sink_demand = demand.to_dict()

    shed_supply = {
        shed: sum([source_supply.get(source, 0) for source in shed_sources[shed]])
        for shed in shed_sources
    }
    shed_demand = {
        shed: sum([sink_demand.get(sink, 0) for sink in shed_sinks[shed]])
        for shed in shed_sinks
    }

    for shed, total_supply in shed_supply.items():
        total_demand = shed_demand[shed]
        if total_demand > total_supply:
            print_message(
                "WARNING: supply shed has excess demand, LP will not find solution unless option `allow_deviation=True` is used",
                "warn",
            )
            print_message("", "warn")
            print_message("    sources / supply", "warn")
            print_message("", "warn")
            for source in shed_sources[shed]:
                if source in source_supply:
                    print_message(
                        f"    {str(source).ljust(16)}    {str(int(source_supply[source])).rjust(12)}",
                        "warn",
                    )
            print_message(
                f"    total supply        {str(int(total_supply)).rjust(12)}",
                "warn",
            )
            print_message("", "warn")
            print_message("    sinks / demand", "warn")
            print_message("", "warn")
            for sink in shed_sinks[shed]:
                if sink in sink_demand:
                    print_message(
                        f"    {str(sink).ljust(16)}    {str(int(sink_demand[sink])).rjust(12)}",
                        "warn",
                    )
            print_message(
                f"    total demand        {str(int(total_demand)).rjust(12)}",
                "warn",
            )
            print_message("", "warn")
