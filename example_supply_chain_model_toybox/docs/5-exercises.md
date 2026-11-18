# 5. Exercises

The exercises go from reading the results to changing the model itself. Each run
rebuilds everything from `data/`, so you can experiment freely and get back to the
original with `git checkout -- .`.

The tests in `tests/` compare against the original results, so they will fail once you
change the data or model. That is expected.

## Reading the model

**1. Trace a shipment.** `Farm_Green1` (asset 100001) exports 50 t to Caramelia. Find
its rows in `results.csv`. Why is it split in two? Which municipality outside Toffee
Flats contributes, and why that one? *Hint:* look at the Toffee Flats row in the LP
table in [How the model works](2-how-the-model-works.md#step-2-linear-programming).

**2. Rank the importers.** Work out deforestation per tonne for each importing company.
Then work out what share of each importer's volume is `UNKNOWN`. Would you rank them
differently once you know that?

**3. Predict, then check.** Before running anything: if Gumdrop Hills' deforestation
doubled to 3,000 ha, which destination countries' totals would change? Change
`data/production_2017.csv`, run the model and see if you were right.

## Changing the data

**4. Close a road.** Set the distance between Toffee Flats (102) and Fudge Falls (201)
to 9999 in both directions in `data/distances.csv`. Where does the Toffee Flats hub get
its extra candyflower now? Does any shipment's deforestation change?

**5. Add a year.** Create `production_2018.csv` and `customs_2018.csv` with made-up
numbers and run `SupplyChain("orvessa/candy", 2018)`. Before it works properly you
will need to find what in `definition.py` is fixed to 2017.

## Changing the model

**6. Trace the offices.** A fifth of exported volume goes through offices (level 5) and
stays `UNKNOWN`. Add a branch to `decision_tree` that gives these flows a hub, using an
assumption you can justify. For example: an office exports candyflower collected
by the nearest silo of *any* company. How much does the `UNKNOWN` share drop, and how
do Bonbonia's and Licoricia's deforestation totals change? Write down the assumption
you made: in a real model it has to be published.

**7. Feed the home market locally.** The model assumes untraced exports and domestic
demand draw on the unclaimed pool in the same proportions (see
[Known limitations](3-reading-the-results.md#known-limitations)). Suppose instead that
Orvessans eat candy grown in the south (S2 and S3) first, and untraced exports take
whatever is left. Change `append_domestic_demand` and `embed_deforestation` to match.
What happens to the pool intensity used for untraced exports, and to Bonbonia's total?
`quality_assurance.py` already checks that no municipality supplies more than it
produced and that every hectare is attributed, so it will tell you if you get the
bookkeeping wrong.

**8. Put bounds on the estimate.** Untraced exports carry the pool's *average*
intensity. Work out the lowest and highest deforestation the 260 t could carry if
they came from the lowest-intensity or highest-intensity municipalities in the pool
(fill from the cleanest or dirtiest first, up to each municipality's unclaimed
volume). Report Bonbonia's deforestation as a range instead of a single number. How
would you show this uncertainty to a reader?

**9. Account for processing losses.** Suppose 1 t of candyflower makes only 0.8 t of
candy. Customs volumes for candy (`hs6 == "990002"`) must then be converted back to
candyflower equivalent before the LP, or factories will look like they need too little.
Where in the code would you do the conversion? Which columns should be converted, and
which kept as they are?

## Going further

**10. Build a second commodity.** Invent a second product for Orvessa (say, *gumwood*)
in `trase/models/orvessa/gumwood/`, with its own data and definition. Move anything
the two models share, such as the municipality list, into a `preparation.py` in
`trase/models/orvessa/` so both can use it (see
[Where models live](4-building-your-own-model.md#where-models-live)).

---

Previous: [4. Building your own model](4-building-your-own-model.md) · Back to the [README](../README.md)
