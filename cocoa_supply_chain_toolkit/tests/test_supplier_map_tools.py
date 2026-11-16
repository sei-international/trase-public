"""
Small tests of supplier_map/supplier_map_tools.py on made-up data.
Run from the toolkit's top folder:  python3 tests/test_supplier_map_tools.py
"""
import os
import sys

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "supplier_map"))
import supplier_map_tools as sm  # noqa: E402

ok = True
def check(name, cond):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + name)

check("normalise_text strips accents", sm.normalise_text("  Société Coopérative ") == "SOCIETE COOPERATIVE")
check("normalise_text empty -> None", sm.normalise_text("") is None)

m = sm.build_fuzzy_map(["COOPERATIVE AGRICOLE BENKADIS"], ["SOCIETE COOPERATIVE AGRICOLE BENKADI", "UNION DE ZADI"], verbose=False)
check("fuzzy map finds close name", m.get("BENKADIS") == "SOCIETE COOPERATIVE AGRICOLE BENKADI")
check("fuzzy map rejects distant name", "BENKADY" not in sm.build_fuzzy_map(["COOPERATIVE BENKADY"], ["SOCIETE COOPERATIVE AGRICOLE BENKADI"], verbose=False))

regions = gpd.GeoDataFrame({"CODE": ["R1", "R2"], "NAME": ["Nord", "Sud"]},
                           geometry=[box(0, 1, 1, 2), box(0, 0, 1, 1)], crs="EPSG:4326")
df = pd.DataFrame({
    "AREA": ["nord", "Village X", None, "", None],
    "ACR": ["A", "B", "C", "D", "E"],
    "LAT": [None, None, None, None, 0.5],
    "LON": [None, None, None, None, 0.5],
})
ref = pd.DataFrame({"ACR": ["C"], "CODE": ["R2"], "NAME": ["Sud"]})
out = sm.locate_suppliers(df, regions, area_col="AREA", acronym_col="ACR", lat_col="LAT", lon_col="LON",
                          region_code_col="CODE", region_name_col="NAME",
                          fix_area_names={"VILLAGE X": "SUD"}, area_from_acronym={"D": "NORD"},
                          reference=ref, reference_acronym_col="ACR", reference_code_col="CODE",
                          reference_name_col="NAME")
got = dict(zip(out["ACR"], out["REGION_CODE"]))
check("locate: by name", got.get("A") == "R1")
check("locate: by fix table", got.get("B") == "R2")
check("locate: by reference list", got.get("C") == "R2")
check("locate: by acronym", got.get("D") == "R1")
check("locate: by coordinates", got.get("E") == "R2")

links = pd.DataFrame({
    "SUPPLIER_NUMBER": [1, 1, 2, 3], "YEAR": [2024] * 4,
    "TRADER": ["T1", "T1", None, None],
    "DISCLOSED_BY": ["T1", "T1", "MAKER", "RAINFOREST ALLIANCE"],
    "CERTIFICATION": ["RA", "FT", None, "RA"],
})
l = sm.make_links(links, 2024)
check("make_links: one row per supplier x buyer", len(l) == 3)
check("make_links: buyer falls back to discloser", l.loc[l.SUPPLIER_NUMBER == 2, "BUYER"].item() == "MAKER")
check("make_links: certification schemes are not buyers", pd.isna(l.loc[l.SUPPLIER_NUMBER == 3, "BUYER"].item()))
check("make_links: certifications combined", l.loc[l.SUPPLIER_NUMBER == 1, "CERTIFICATIONS"].item() == "FT + RA")
check("make_links: trader flag", bool(l.loc[l.SUPPLIER_NUMBER == 1, "BUYER_IS_TRADER"].item()))

# the synthetic example tables pass the checks
d = os.path.join(ROOT, "data", "synthetic_cote_divoire")
long = pd.read_csv(os.path.join(d, "supplier_map", "supplier_links_2024.csv"))
sup = pd.read_csv(os.path.join(d, "supplier_map", "suppliers_2024.csv"))
codes = gpd.read_file(os.path.join(d, "regions", "departments.geojson"))["LVL_4_CODE"]
check("check_model_tables passes on example data", sm.check_model_tables(long, sup, codes) == [])
bad = long.astype({"BUYER_IS_TRADER": object}); bad.loc[0, "BUYER_IS_TRADER"] = "maybe"
check("check_model_tables catches a bad trader flag", len(sm.check_model_tables(bad, sup, codes)) == 1)

# the spreadsheet template has exactly the columns the model expects,
# and the filled-in example passes the checks
t = os.path.join(ROOT, "supplier_map", "templates")
blank_links = pd.read_excel(os.path.join(t, "supplier_map_template.xlsx"), sheet_name="supplier_links")
blank_sups = pd.read_excel(os.path.join(t, "supplier_map_template.xlsx"), sheet_name="suppliers")
check("template: supplier_links columns", list(blank_links.columns) == sm.LINK_COLUMNS)
check("template: suppliers columns", list(blank_sups.columns) == sm.SUPPLIER_COLUMNS)
ex = os.path.join(t, "supplier_map_example.xlsx")
check("example spreadsheet passes check_model_tables",
      sm.check_model_tables(pd.read_excel(ex, sheet_name="supplier_links"),
                            pd.read_excel(ex, sheet_name="suppliers"), codes) == [])

sys.exit(0 if ok else 1)
