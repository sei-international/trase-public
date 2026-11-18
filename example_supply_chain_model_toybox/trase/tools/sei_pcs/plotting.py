from typing import TYPE_CHECKING, Tuple, Union
from textwrap import shorten

import pandas as pd

import numpy as np

if TYPE_CHECKING:  # plotly is optional: only needed for charts
    import plotly

from trase.tools.etl.utilities import consolidate
from trase.tools.sei_pcs.formatting import round_to_significant_digits
from trase.tools.sei_pcs.pandas_utilities import (
    compare_dataframes_single,
    Compare,
)

TRASE_GREY = "#4e6356"
TRASE_RED = "#ff6a5f"
TRASE_GREEN = "#00d19a"
TRASE_PURPLE = "#8b87ff"


def dumbbell_compare(
    df_a,
    df_b,
    value,
    group_by,
    comparator=Compare.absolute_error,
    labels=("Base", "Comparison"),
    colors=(TRASE_GREY, TRASE_RED),
    title_text="",
    xaxis_title="",
    yaxis_title="",
    legend_title="",
    label_width=15,
    shorten_end=False,
    max_rows=15,
    other_label="OTHER",
    include_other=True,
    row_height_px=40,
) -> "plotly.graph_objs.Figure":
    """Compare two dataframes and create a "dumbbell"-style plot.

    Here is an ASCII-art of what that looks like:

          BUNGE │   *─────*
        CARGILL │          *───*
           ADM  │  *─*
          OTHER │  *
                └────────────────
                 0   10   20   30

    Args:
        df_a: base DataFrame.
        df_b: comparison DataFrame.
        value: the name of the column containing numerical data that will be compared.
            Any values duplicated over `group_by` will be summed.
        group_by: a list of categorical columns to group by.
        comparator (optional): a function which takes two series and returns their
            comparison. You can also pass in the string name of a method on
            ``trase.tools.sei_pcs.pandas_utilities.Compare``. See
            ``trase.tools.sei_pcs.pandas_utilities.Compare`` for some examples.
            Defaults to ``Compare.absolute_error``.
        labels (optional): name of the two series that will appear in the legend.
            Default: ("Base", "Comparison").
        title_text (optional): title for the chart. Default ""
        xaxis_title (optional): title for the X-axis. Default ""
        yaxis_title (optional): title for the Y-axis. Default ""
        legend_title (optional): title for the legend. Default ""
        label_width (optional): the maximum length of a label before it is shortened
            with "...". Default: 15
        shorten_end (optional): if `True` labels will be shortened from the end
            ("LONG LA..."); if `False` they will be shortened from the start (e.g.
            "...G LABEL"). Default: False
        max_rows (optional): how many rows to show, or `None` if all rows should be
            shown. Default: 15
        other_label (optional): the name of the "other" category; either a string or a
            tuple of strings of the same length as `group_by`. Default: "OTHER"
        include_other (optional): whether to include the "OTHER". Default: True

    Returns: the plotly Figure
    """
    import plotly.express as px

    # parse some arguments: do this right up top in case it raises an error
    label_a, label_b = labels
    color_a, color_b = colors

    # combine the two dataframes into one, sorting by absolute error
    df = compare_dataframes_single(
        df_a, df_b, value, group_by, comparator, sort="descending"
    )

    # rename the "total" columns to the desired label
    df = df.rename(columns={"total_a": label_a, "total_b": label_b}, errors="raise")
    df = df[[label_a, label_b, "comparison"]]

    # either truncate the dataframe at max rows, or collapse into an "OTHER" section
    df["label"] = df.index
    if max_rows is not None:
        df, df_other = df[:max_rows], df[max_rows:]
        if include_other:
            df_other["label"] = other_label
            df_other = df_other.groupby("label").sum().reset_index()
            assert set(df.columns) == set(df_other.columns)
            df = pd.concat([df, df_other], sort=False)

    # convert index to strings
    df["label"] = df["label"].apply(lambda l: render_label(l, shorten_end, label_width))

    # sort from big to small
    df = df.loc[::-1].reset_index(drop=True)

    # plot circles at the ends of the dumbbell
    fig = px.scatter(
        df,
        x=[label_a, label_b],
        y="label",
        labels={"variable": legend_title},
        color_discrete_map={label_a: color_a, label_b: color_b},
    )

    # resize and add titles
    fig.update_layout(
        title_text=title_text,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        height=row_height_px * len(df) + len(group_by) * 50,
    )
    fig.update_yaxes(scaleratio=2, type="category")

    # add lines between the circles
    for _, row in df.iterrows():
        a, b = row[label_a], row[label_b]
        fig.add_shape(
            type="line",
            x0=min(a, b),
            y0=row["label"],
            x1=max(a, b),
            y1=row["label"],
            line_color=color_b if a < b else color_a,
            ysizemode="scaled",
        )

    return fig


def sankey(
    df,
    value_column,
    categorical_columns,
    title_text="",
    shorten_end=False,
    label_width=15,
) -> "plotly.graph_objs.Figure":
    """
    Args:
        df: the dataframe to be rendered. You do not need to consolidate the dataframe,
            this will be done for you in the function.
        value_column: the column which will be used for the widths of the flows
        categorical_columns: the columns which will be used for the columns of the
            Sankey.
        title_text (optional): title for the chart. Default ""
        label_width (optional): the maximum length of a label before it is shortened
            with "...". Default: 15
        shorten_end (optional): if `True` labels will be shortened from the end
            ("LONG LA..."); if `False` they will be shortened from the start (e.g.
            "...G LABEL"). Default: False

    Returns: the plotly Figure
    """

    import plotly.graph_objects as go

    # consolidate the dataframe over the desired columns
    df = consolidate(df, [value_column], categorical_columns)

    # First we line up the the nodes of the Sankey in an order, assigning each a number 0, 1, 2...:
    #
    #   {
    #     "column1": {"column1-value1": 0, "column1-value2": 1},
    #     "column2": {"column2-value2": 2, "column2-value2": 3},
    #   }
    #
    indexes = {}
    offset = 0
    for column in categorical_columns:
        values = df[column].unique()
        indexes[column] = {value: offset + i for (i, value) in enumerate(values)}
        offset += len(values)

    # make a flat list of labels this order
    #
    #   ["column1-value1", "column1-value2", "column2-value1", "column2-value2"]
    #
    labels = [
        render_label(label, shorten_end, label_width)
        for values in indexes.values()
        for label in values.keys()
    ]

    # now make a dataframe of sources and targets
    #
    #   | source | target | value |
    #   |--------|--------|-------|
    #   |      0 |      2 |   100 |
    #   |      0 |      3 |   150 |
    #   |      1 |      2 |   200 |
    #   |      1 |      3 |   250 |
    #
    data = pd.concat(
        pd.DataFrame(
            {
                "source": df[source].map(indexes[source]),
                "target": df[target].map(indexes[target]),
                "value": df[value_column],
            }
        )
        for (source, target) in zip(categorical_columns[:-1], categorical_columns[1:])
    )

    # this gets passed to go.Sankey
    fig = go.Figure(
        data=[
            go.Sankey(
                node=dict(
                    pad=15,
                    thickness=20,
                    line=dict(width=0),
                    label=labels,
                    color="#ff6a5f",
                ),
                link=data.to_dict("list"),
            )
        ]
    )
    fig.update_layout(title_text=title_text)
    return fig


def histogram_compare(
    df_a,
    df_b,
    value,
    group_by,
    comparator=Compare.absolute_error,
    title_text="",
    scale_by="none",
    bins=15,
    significant_digits=2,
    decimal_points=0,
    posinf_label="only in b",
    neginf_label="only in a",
):
    import plotly.graph_objects as go

    if isinstance(comparator, str):
        comparator = getattr(Compare, comparator)

    # compare the dataframes
    df = compare_dataframes_single(df_a, df_b, value, group_by, comparator)

    # split into finite and infinite values
    df_posinf = df[np.isposinf(df["comparison"])]
    df_neginf = df[np.isneginf(df["comparison"])]
    df = df[np.isfinite(df["comparison"])]

    # calculate bins for finite values
    weights = {"none": None, "a": df["total_a"], "b": df["total_b"]}[scale_by]
    heights, bin_edges = np.histogram(df["comparison"], bins, weights=weights)

    def f(x):
        return (
            f"{round_to_significant_digits(x, significant_digits):,.{decimal_points}f}"
        )

    bin_labels = [f"{f(a)} to {f(b)}" for (a, b) in zip(bin_edges[:-1], bin_edges[1:])]
    colours = [
        TRASE_PURPLE if end < 0 else TRASE_GREEN if start > 0 else TRASE_GREY
        for (start, end) in zip(bin_edges[:-1], bin_edges[1:])
    ]

    # add any bins for infinite values
    if not df_neginf.empty and scale_by != "b":
        bin_labels = [neginf_label, *bin_labels]
        w = {"none": len(df_neginf), "a": df_neginf["total_a"].sum()}[scale_by]
        heights = [w, *heights]
        colours = [TRASE_GREEN, *colours]

    if not df_posinf.empty and scale_by != "a":
        bin_labels = [*bin_labels, posinf_label]
        w = {"none": len(df_posinf), "b": df_posinf["total_b"].sum()}[scale_by]
        heights = [*heights, w]
        colours = [*colours, TRASE_PURPLE]

    # create the plot
    ylabel = {"none": "count", "a": f"{value}_a", "b": f"{value}_b"}[scale_by]
    xlabel = f"{value}, {comparator.__name__}"
    fig = go.Figure(data=[go.Bar(x=bin_labels, y=heights, marker_color=colours)])
    fig.update_layout(title_text=title_text, yaxis_title=ylabel, xaxis_title=xlabel)
    return fig


def shorten_label(label: str, shorten_end=False, label_width=15) -> str:
    """Trims labels that are too long and adds '...'"""
    i = -1 if shorten_end else 1
    label = label[::i]
    label = shorten(label, width=label_width, placeholder="...")
    return label[::i]


def render_label(value: Union[Tuple, str], shorten_end=False, label_width=15) -> str:
    """Plotly cannot render pd.MultiIndex, so we convert the tuples to strings.
    This function works both on MultiIndex (tuples) or Index (strings).
    """
    labels = value if isinstance(value, tuple) or isinstance(value, list) else [value]
    ret = "<br>".join(
        [shorten_label(str(label), shorten_end, label_width) for label in labels]
    )

    # unfortunately Plotly tries to be too clever and interprets strings as numbers if
    # they contain digits. this causes problems later when we refer to the y-values as
    # categories rather than y-coordinates:
    # https://github.com/plotly/plotly.py/issues/1918
    # to get around this we add a character to the start of any label which contains
    # numbers. I tried to insert a non-printable UTF8 character, but this caused an
    # error when rendering to PNG. So I settled on » as the least-invasive prefix
    try:
        float(ret)  # if this does not error, the string is a number
        return f"» {ret}"
    except ValueError:
        return ret


# A colour-blind-safe categorical order. Hues are assigned to entities in this fixed
# order and never cycled: a chart with more entities than there are slots draws the
# remainder in a single muted colour rather than reusing a hue.
CATEGORICAL_PALETTE = (
    "#2a78d6",  # blue
    "#eb6834",  # orange
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e87ba4",  # magenta
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
)
MUTED_GREY = "#9a9a94"

# Line styles used, in order, once the palette's hues have all been assigned once.
LINE_DASHES = ("solid", "dash", "dot", "longdashdot")


def _cycle_styles(palette_size, n_entities):
    """Yield a line dash per entity: solid for the first pass over the palette, then
    a new dash each time the hues are reused, so hue and dash together stay unique.
    """
    for i in range(n_entities):
        yield LINE_DASHES[min(i // palette_size, len(LINE_DASHES) - 1)]


def bump_chart(
    df,
    period,
    entity,
    value,
    period_order=None,
    max_rank=10,
    max_entities=12,
    palette=CATEGORICAL_PALETTE,
    title_text="",
    value_format="{:,.1f}",
    value_suffix="",
    label_width=24,
    marker_size=11,
    row_height_px=34,
    label_margin_px=230,
    width=1000,
    dividers=(),
) -> "plotly.graph_objs.Figure":
    """Plot how entities change rank from one period to the next (a "bump chart").

    Within each period the entities are ranked by ``value`` (rank 1 = largest), and
    each entity's rank is drawn as a line running left to right, so a crossing means
    one entity overtook another. Entities are labelled directly at both ends of their
    line, so identity never depends on colour alone.

    Here is an ASCII-art of what that looks like::

               2019  2020  2021
          1  ─  A─────A     B
                        ╲ ╱
          2  ─  B─────B  ╳  A
                        ╱ ╲
          3  ─  C─────C     C

    Args:
        df: a pandas DataFrame in long form, with one row per (``period``,
            ``entity``). Values duplicated over that pair are summed.
        period: name of the column holding the period (usually a year). Periods are
            drawn evenly spaced in the order given by ``period_order``.
        entity: name of the column holding the entity being ranked.
        value: name of the numeric column the ranking is based on.
        period_order (optional): the periods to draw, in order. Periods in ``df`` but
            not in this list are dropped, which is how you restrict the chart to a
            span of years. Default: every period in ``df``, sorted.
        max_rank (optional): only entities reaching this rank or better in at least
            one period are drawn. Default: 10.
        max_entities (optional): a hard ceiling on how many lines are drawn, applied
            after ``max_rank``. Over a long span many more entities touch the top
            ``max_rank`` than are on screen at once, and past a dozen lines the chart
            stops being readable; the ones kept are those with the best rank, ties
            broken by total ``value``. Pass ``None`` for no ceiling. Default: 12.
        palette (optional): the fixed hue order used for the entities, assigned in
            order of best-ever rank. Default: ``CATEGORICAL_PALETTE``.
        title_text (optional): title for the chart. Default: "".
        value_format (optional): a ``str.format`` spec for the value shown in the
            hover label and in the end-of-line labels. Default: ``"{:,.1f}"``.
        value_suffix (optional): appended to the formatted value, e.g. ``" Mt"``.
            Default: "".
        label_width (optional): entity labels longer than this are truncated with
            "...". Default: 24.
        marker_size / row_height_px / label_margin_px / width (optional): layout
            tuning. ``label_margin_px`` is the room reserved either side for the
            direct labels.
        dividers (optional): an iterable of ``(period_before, text)`` pairs. Each
            draws a labelled vertical rule immediately after that period — for
            marking, say, a model-version boundary. Default: no rules.

    Returns: the plotly Figure.

    Raises:
        ValueError: if no entity reaches ``max_rank``, or if a divider names a period
            that is not being drawn.
    """
    import plotly.graph_objects as go

    totals = df.groupby([period, entity], as_index=False)[value].sum()
    if period_order is None:
        period_order = sorted(totals[period].unique())
    else:
        period_order = list(period_order)
        totals = totals[totals[period].isin(period_order)]
    position = {p: i for i, p in enumerate(period_order)}

    totals["rank"] = (
        totals.groupby(period)[value].rank(method="first", ascending=False).astype(int)
    )

    # Style follows the entity, keyed on its best-ever rank — so adding a period, or
    # raising `max_rank`, never restyles the entities that were already on the chart.
    best_rank = totals.groupby(entity)["rank"].min()
    grand_total = totals.groupby(entity)[value].sum()
    shown = sorted(
        best_rank[best_rank <= max_rank].index,
        key=lambda e: (best_rank[e], -grand_total[e]),
    )
    if not shown:
        raise ValueError(f"No entity reaches rank {max_rank}; nothing to plot")
    if max_entities is not None:
        shown = shown[:max_entities]
    # More entities usually reach the top `max_rank` over the whole span than there are
    # hues in the palette. Rather than inventing hues, entities past the end of the
    # palette reuse them under a second and third line style: identity is then carried
    # by hue *and* dash together, and by the direct labels either way.
    styles = [
        (palette[i % len(palette)], dash)
        for i, dash in zip(range(len(shown)), _cycle_styles(len(palette), len(shown)))
    ]

    def label(name):
        return shorten_label(str(name), shorten_end=True, label_width=label_width)

    first_period = period_order[0]
    fig = go.Figure()
    for (colour, dash), name in zip(styles, shown):
        series = totals[totals[entity] == name].set_index(period)
        periods = [p for p in period_order if p in series.index]
        fig.add_trace(
            go.Scatter(
                x=[position[p] for p in periods],
                y=[series.loc[p, "rank"] for p in periods],
                mode="lines+markers",
                name=label(name),
                line=dict(color=colour, width=2, dash=dash),
                # A ring in the surface colour keeps overlapping markers readable
                # where several lines pass through the same rank.
                marker=dict(
                    size=marker_size,
                    color=colour,
                    line=dict(width=2, color="white"),
                ),
                customdata=[
                    (p, value_format.format(series.loc[p, value]) + value_suffix)
                    for p in periods
                ],
                hovertemplate=(
                    f"<b>{name}</b><br>%{{customdata[0]}}<br>"
                    "rank %{y}<br>%{customdata[1]}<extra></extra>"
                ),
                showlegend=False,
            )
        )
        # Direct labels at both ends, so the chart stays readable without reference to
        # the colours. The left-hand label is only drawn for an entity present in the
        # first period — otherwise it would float in the middle of the plot — and the
        # right-hand one carries the value as well.
        ends = [
            (
                periods[-1],
                "left",
                f"  {label(name)}  "
                f"{value_format.format(series.loc[periods[-1], value])}{value_suffix}",
            )
        ]
        if periods[0] == first_period:
            # The rank rides on the left-hand label rather than on a y-axis tick: the
            # labels have to spill into the margin to fit, which is exactly where the
            # tick labels would otherwise sit.
            ends.append(
                (
                    periods[0],
                    "right",
                    f"{series.loc[periods[0], 'rank']}  {label(name)}  ",
                )
            )
        for p, anchor, text in ends:
            fig.add_annotation(
                x=position[p],
                y=series.loc[p, "rank"],
                text=text,
                showarrow=False,
                xanchor=anchor,
                font=dict(size=11, color="#3d3d3d"),
            )

    for period_before, text in dividers:
        if period_before not in position:
            raise ValueError(f"Divider period {period_before!r} is not being drawn")
        fig.add_vline(
            x=position[period_before] + 0.5,
            line_dash="dot",
            line_color=MUTED_GREY,
            annotation_text=text,
            annotation_position="top",
            annotation_font=dict(size=11, color="#3d3d3d"),
        )

    n_ranks = int(totals[totals[entity].isin(shown)]["rank"].max())
    n_ranks = min(max_rank, n_ranks)
    fig.update_layout(
        title_text=title_text,
        width=width,
        height=row_height_px * n_ranks + 150,
        margin=dict(l=label_margin_px, r=label_margin_px, t=80, b=40),
        plot_bgcolor="white",
        hovermode="closest",
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=list(position.values()),
        ticktext=[str(p) for p in period_order],
        showgrid=True,
        gridcolor="#ededea",
        # Leave room either side for the direct labels.
        range=[-0.35, len(period_order) - 0.65],
    )
    fig.update_yaxes(
        # No axis title or tick labels: the rank is printed on the left-hand entity
        # label, and anything drawn in the axis gutter collides with those labels.
        tickvals=list(range(1, n_ranks + 1)),
        showticklabels=False,
        showgrid=True,
        gridcolor="#f4f4f1",
        zeroline=False,
        range=[n_ranks + 0.6, 0.4],
    )
    return fig
