"""
Check deforestation_metrics/reshape_earth_engine_exports.py on made-up GEE
exports (Côte d'Ivoire-style and Ghana-style region codes):
  - region codes become region IDs
  - each band ends up in the right metric column and year
  - higher administrative levels and the country are sums of their regions
  - cocoa metrics start at the chosen first year
Run from the toolkit's top folder:  python3 tests/test_earth_engine_exports.py
"""
import os
import random
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "deforestation_metrics"))
import reshape_earth_engine_exports as rg  # noqa: E402

random.seed(1)
ok = True


def check(passed, what):
    global ok
    ok &= bool(passed)
    print(("PASS " if passed else "FAIL ") + what)


def fake_exports(folder, code):
    if code == "ci":
        regions = [dict(LVL_4_CODE=f"CI-{a}.{b}.{c}_1", LVL_4_NAME=f"D{a}{b}{c}", LVL_3_CODE="x")
                   for a in (1, 2, 12) for b in (1, 2) for c in (1, 3)]
    else:
        regions = [dict(GID_2=f"GHA.{a}.{b}_1", NAME_2=f"D{a}{b}", GID_0="GHA") for a in (1, 3) for b in (1, 2, 10)]
    bands = {
        "eth2021_cocoa_tmfloss_annual_ha": [f"cd_1yr_tmf_{t}_{y}" for y in range(2010, 2025) for t in ("loss", "def", "deg")],
        "eth2021_cocoa_tmfloss_total_15yr": [f"cd_15yr_tmf_{t}_{y}" for y in range(2010, 2025) for t in ("loss", "def", "deg")],
        "ghg_cd_gross_1yr": [f"ghg_cd_1yr_gross_{y}" for y in range(2010, 2025)],
        "ghg_cd_gross_15yr": [f"ghg_cd_15yr_gross_{y}" for y in range(2010, 2025)],
        "ghg_cd_net_1yr": [f"ghg_cd_1yr_net_{y}" for y in range(2010, 2025)],
        "ghg_cd_net_15yr": [f"ghg_cd_15yr_net_{y}" for y in range(2010, 2025)],
        "ghg_territorial_gross_1yr": [f"ghg_uTMF_def_1yr_gross_{y}" for y in range(2000, 2025)],
        "territorial_tmfloss_annual_ha": [f"uTMF_1yr_{t}_{y}" for y in range(2000, 2025) for t in ("lost_by", "defo_by", "degr_by")],
        "undisturbed_tmf_yearly": [f"uTMF_remaining{y}" for y in range(2000, 2025)],
    }
    tables = {}
    for name, cols in bands.items():
        rows = []
        for r in regions:
            row = {"system:index": "x", **r, ".geo": "{}"}
            row.update({c: round(random.uniform(0, 500), 3) for c in cols})
            rows.append(row)
        tables[name] = pd.DataFrame(rows)
        tables[name].to_csv(os.path.join(folder, f"{name}_{code}.csv"), index=False)
    return tables


check(rg.ci_code_to_region_id("CI-3.1.2_1") == "CI-030102", "Côte d'Ivoire code CI-3.1.2_1 -> CI-030102")
check(rg.gadm_code_to_region_id("GHA.3.10_1") == "GH-03.10", "GADM code GHA.3.10_1 -> GH-03.10")

for code, region_col, first_id in (("ci", "LVL_4_CODE", "CI-12.2.3_1"), ("gh", "GID_2", "GHA.3.10_1")):
    with tempfile.TemporaryDirectory() as d:
        gee = fake_exports(d, code)
        out = rg.reformat(d, code, cocoa_min_year=2014)
    settings = rg.COUNTRIES[code]
    rid = settings["to_region_id"](first_id)
    cocoa = out["c_def_emission"]

    # one band -> one metric, for one region and year
    raw = gee["eth2021_cocoa_tmfloss_total_15yr"]
    want = raw.loc[raw[region_col] == first_id, "cd_15yr_tmf_loss_2020"].iloc[0]
    got = cocoa.loc[(cocoa.REGION_ID == rid) & (cocoa.YEAR == 2020),
                    "COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL"].iloc[0]
    check(np.isclose(got, want), f"{code}: band cd_15yr_tmf_loss_2020 -> COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL, 2020")
    raw = gee["ghg_cd_net_1yr"]
    want = raw.loc[raw[region_col] == first_id, "ghg_cd_1yr_net_2021"].iloc[0]
    got = cocoa.loc[(cocoa.REGION_ID == rid) & (cocoa.YEAR == 2021), "COCOA_NET_EMISSIONS_ANNUAL"].iloc[0]
    check(np.isclose(got, want), f"{code}: band ghg_cd_1yr_net_2021 -> COCOA_NET_EMISSIONS_ANNUAL, 2021")

    # the country row is the sum of the regions
    n_regions = len(gee["ghg_cd_net_1yr"])
    regions_only = cocoa[cocoa.REGION_ID.str.len() == len(rid)]
    country = cocoa[cocoa.REGION_ID == settings["national_id"]]
    check(len(regions_only.REGION_ID.unique()) == n_regions, f"{code}: one ID per region ({n_regions})")
    s = regions_only.groupby("YEAR")["COCOA_GROSS_EMISSIONS_15_YEARS_TOTAL"].sum()
    c = country.set_index("YEAR")["COCOA_GROSS_EMISSIONS_15_YEARS_TOTAL"]
    check(np.allclose(s.sort_index().values, c.sort_index().values), f"{code}: country = sum of regions")

    check(cocoa.YEAR.min() == 2014, f"{code}: cocoa metrics start at the chosen first year (2014)")
    check(out["def"].YEAR.min() == 2000, f"{code}: territorial metrics keep all years")
    check(not any(t.isna().any().any() for t in out.values()), f"{code}: no missing values")

# optional cocoa area and production exports
with tempfile.TemporaryDirectory() as d:
    pd.DataFrame({"LVL_4_CODE": ["CI-3.1.2_1", "CI-12.1.1_1"], "sum": [100.5, 20.0]}).to_csv(f"{d}/a.csv", index=False)
    pd.DataFrame({"REGION_ID": ["CI-3.1.2_1", "CI-12.1.1_1"], "production_2020": [50.0, 5.0],
                  "production_2021": [60.0, 6.0]}).to_csv(f"{d}/p.csv", index=False)
    area = rg.reshape_cocoa_area(f"{d}/a.csv", "ci")
    prod = rg.reshape_cocoa_production(f"{d}/p.csv", "ci")
check(list(area.columns) == ["REGION_ID", "COCOA_HA"] and area.REGION_ID.tolist() == ["CI-030102", "CI-120101"],
      "cocoa area export -> REGION_ID, COCOA_HA")
check(list(prod.columns) == ["REGION_ID", "YEAR", "COCOA_TONNES"] and len(prod) == 4 and
      prod.loc[(prod.REGION_ID == "CI-120101") & (prod.YEAR == 2021), "COCOA_TONNES"].item() == 6.0,
      "cocoa production export -> REGION_ID, YEAR, COCOA_TONNES")

sys.exit(0 if ok else 1)
