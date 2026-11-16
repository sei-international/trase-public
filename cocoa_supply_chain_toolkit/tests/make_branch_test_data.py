"""
Build a TEST dataset that exercises every special case in the model, for
tests/test_model_results.R. It copies the synthetic Côte d'Ivoire example data
and adds fictional records that trigger the branches the example does not:

  - a union of cooperatives (ECOOKIM) exporting for three member cooperatives
  - an exporting cooperative whose acronym (SCAT) is shared by two suppliers,
    resolved by the full-name pattern in exporting_cooperative_shared_acronyms.csv
  - a licensed buyer (BIOPARTENAIRE) whose exporter group has another name
  - a Cocoa & Forests Initiative signatory (CARGILL) importing from a
    non-disclosing exporter while also exporting itself

The company names match the Côte d'Ivoire settings in countries/cote_divoire/;
all volumes, links and farmer numbers are invented. Not for analysis.

Usage: python3 tests/make_branch_test_data.py   (from the toolkit's top folder)
Writes: tests/data_branch_coverage/
"""
import csv
import os
import random
import shutil

random.seed(7)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "synthetic_cote_divoire")
DST = os.path.join(ROOT, "tests", "data_branch_coverage")
shutil.rmtree(DST, ignore_errors=True)
shutil.copytree(SRC, DST)


def append(rel, rows, delim=";"):
    path = os.path.join(DST, rel)
    with open(path, newline="", encoding="utf-8") as f:
        header = next(csv.reader(f, delimiter=delim))
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=delim)
        for r in rows:
            w.writerow(["NA" if r.get(h) is None else r.get(h) for h in header])


def last_id(rel, col):
    with open(os.path.join(DST, rel), newline="", encoding="utf-8") as f:
        return max(int(r[col]) for r in csv.DictReader(f))


geo = ["CI-2.3.1_1", "CI-8.2.2_1", "CI-5.1.1_1"]
next_id = last_id("supplier_map/suppliers_2024.csv", "SUPPLIER_NUMBER") + 1
long_rows, coop_rows = [], []
flow = 9000

def coop(acr, full, g, buyer=None, trader=None, n=None):
    global next_id, flow
    flow += 1
    cid = next_id
    next_id += 1
    coop_rows.append(dict(SUPPLIER_NUMBER=cid, YEAR=2024, SUPPLIER_SHORT_NAME=acr, SUPPLIER_NAME=full,
                          REGION_CODE=g, CERTIFIED="FALSE"))
    long_rows.append(dict(LINK_ID=f"2024-{flow}", SUPPLIER_NUMBER=cid, YEAR=2024, SUPPLIER_SHORT_NAME=acr,
                          SUPPLIER_NAME=full, REGION_CODE=g, BUYER=buyer,
                          BUYER_IS_TRADER="TRUE" if trader else "FALSE", NUMBER_OF_FARMERS=n,
                          DISCLOSED_BY=buyer, CERTIFIED=None if buyer is None else "FALSE"))

# union of cooperatives and its members
for i, g in enumerate(geo):
    coop(f"TESTMEMBER{i}", f"COOPERATIVE TEST MEMBRE {i}", g, buyer="ECOOKIM")
coop("ECOOKIM", "UNION DES COOPERATIVES TEST", geo[0], buyer="ECOOKIM")
# two suppliers sharing the acronym SCAT; only the TOUIH one is the exporter
coop("SCAT", "SOCIETE COOPERATIVE AGRICOLE DE TOUIH", geo[1])
coop("SCAT", "SOCIETE COOPERATIVE AUTRE TEST", geo[2])
# a supplier of CARGILL, so that CARGILL is a disclosing trader
coop("TESTCARG", "COOPERATIVE TEST FOURNISSEUR", geo[2], buyer="CARGILL", trader="CARGILL", n=400)

append("supplier_map/supplier_links_2024.csv", long_rows, delim=",")
append("supplier_map/suppliers_2024.csv", coop_rows, delim=",")

append("licensed_buyers/licensed_buyers_2021.csv",
       [dict(NOM="TEST REPRESENTANT", DENOMINATION="BIOPARTENAIRE", ZONE_DACTIVITE="X", LVL_4_CODE=geo[0])])

trade = []
def ship(exporter, importer, t, hs6="180100", hs10="1801001100", dest="NETHERLANDS"):
    trade.append(dict(COUNTRY_OF_ORIGIN="COTE D'IVOIRE", COUNTRY_OF_DESTINATION=dest, YEAR=2024,
                      HS6=hs6, HS_CODE=hs10, EXPORTER=exporter, BUYER=importer,
                      NET_WEIGHT_TON=t, CIF_USD=round(t * 2900, 2)))
for _ in range(4):
    ship("ECOOKIM", "NORDHAVEN COCOA BV", round(random.uniform(200, 900), 3))
    ship("STE COOP AGRI DE TOUIH", "SOLENT FOODS LTD", round(random.uniform(50, 300), 3))
    ship("BIOPARTENAIRE", "PORTLAND CACAO INC", round(random.uniform(200, 900), 3))
    ship("CARGILL WEST AFRICA", "RIVERSIDE GRINDING GMBH", round(random.uniform(500, 2000), 3))
    ship("FALAISE AGRO", "CARGILL COCOA", round(random.uniform(200, 900), 3))   # -> counted under CARGILL
append("customs/cocoa_exports_2024.csv", trade)
print("wrote", DST)
