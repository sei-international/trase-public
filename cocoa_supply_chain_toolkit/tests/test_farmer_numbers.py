"""
Check supplier_map_tools.impute_farmer_numbers() on small hand-made cases, one
per rule (see the function's docstring and docs/HOW_THE_MODEL_WORKS.md, Step 5).
Run from the toolkit's top folder:  python3 tests/test_farmer_numbers.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "supplier_map"))
import supplier_map_tools as sm  # noqa: E402

COLS = ["COOP", "YEAR", "COMPANY", "TRADER", "FARMERS"]
current = pd.DataFrame([
    # coop A: CARGILL disclosed 100 this year; OLAM disclosed nothing
    ("A", 2024, "CARGILL", "CARGILL", 100),
    ("A", 2024, "OLAM", "OLAM", None),
    # coop B: ECOM disclosed nothing this year but 300 last year
    ("B", 2024, "ECOM", "ECOM", None),
    # coop C: two figures from the same company this year -> their mean
    ("C", 2024, "TOUTON", "TOUTON", 200),
    ("C", 2024, "TOUTON", "TOUTON", 301),
    # coop D: nothing this year; another buyer disclosed 500 last year
    ("D", 2024, "SUCDEN", "SUCDEN", None),
    # coop E: only Rainforest Alliance has a figure: not used for buyers
    ("E", 2024, "MARS", None, None),
    ("E", 2024, "RAINFOREST ALLIANCE", None, 999),
    # coop F: nothing anywhere
    ("F", 2024, "CEMOI", "CEMOI", None),
], columns=COLS)
history = pd.DataFrame([
    ("B", 2023, "ECOM", "ECOM", 300),
    ("D", 2023, "BARRY CALLEBAUT", "BARRY CALLEBAUT", 500),
    ("A", 2023, "OLAM", "OLAM", None),
], columns=COLS)

out = sm.impute_farmer_numbers(current, coop_col="COOP", year_col="YEAR", company_col="COMPANY",
                               trader_col="TRADER", disclosed_col="FARMERS", history=history)

ok = True


def check(row, column, expected, what):
    global ok
    got = out.loc[row, column]
    same = (np.isnan(got) and expected is None) or (expected is not None and got == expected)
    ok &= bool(same)
    print(("PASS " if same else "FAIL ") + f"{what} (got {got}, expected {expected})")


check(0, "NUM_FARMERS", 100, "a disclosed figure is kept")
check(1, "NUM_FARMERS", 100, "no figure: mean of other buyers of the cooperative, same year")
check(2, "NUM_FARMERS", 300, "no figure this year: the same buyer's figure from another year")
check(3, "NUM_FARMERS", 250, "two figures from the same buyer: their mean, rounded (250.5 -> 250)")
check(5, "NUM_FARMERS", 500, "no figure this year: other buyers' figures from another year")
check(6, "NUM_FARMERS", None, "certification-scheme figures are not used for buyers")
check(8, "NUM_FARMERS", None, "nothing known: left empty (the model draws a value)")
mean_2024 = np.round(np.mean([100, 100, 300, 250, 250, 500]))
check(8, "NUM_FARMERS_EXTRAPOLATED", mean_2024, "for publication: empty links get the year's mean link size")
same_rows = len(out) == len(current) and (out["COOP"].values == current["COOP"].values).all()
ok &= bool(same_rows)
print(("PASS " if same_rows else "FAIL ") + "one output row per input row, in the same order")
sys.exit(0 if ok else 1)
