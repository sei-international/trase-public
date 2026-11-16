"""
Generate SYNTHETIC input data for the Côte d'Ivoire cocoa 2024 example.

Everything this script writes is MADE UP. It has the same file names, columns
and formats as the real inputs, so that every script in the package runs end to
end. The numbers, companies, cooperatives and shipments are fictional and the
model results produced from them mean nothing.

The one exception is regions/departments.geojson, which holds the real
(public) department boundaries of Côte d'Ivoire. This script does not write it.

Usage (from the package's top folder):
    python3 data/make_synthetic_data.py   # writes into data/synthetic_cote_divoire/
Only the Python standard library is needed.
"""

import csv
import json
import math
import os
import random

random.seed(2024)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "synthetic_cote_divoire")


def write_csv(rel_path, header, rows, delim=";"):
    path = os.path.join(OUT, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=delim)
        w.writerow(header)
        for r in rows:
            w.writerow(["NA" if v is None else v for v in r])
    print("wrote", os.path.relpath(path, HERE), f"({len(rows)} rows)")


# --------------------------------------------------------------------------- #
# Departments (real codes, from the real boundary file)
# --------------------------------------------------------------------------- #
with open(os.path.join(OUT, "regions", "departments.geojson"), encoding="utf-8") as f:
    depts = [ft["properties"] for ft in json.load(f)["features"]]
codes = sorted(d["LVL_4_CODE"] for d in depts)
name_of = {d["LVL_4_CODE"]: d["LVL_4_NAME"] for d in depts}
# Cocoa is grown in the south and west; for the synthetic data we simply pick
# 35 departments, making sure the three departments that the quality-check report names
# explicitly are among them.
must_have = ["CI-2.3.1_1", "CI-8.2.2_1", "CI-5.1.1_1"]
cocoa_codes = must_have + random.sample([c for c in codes if c not in must_have], 32)

# --------------------------------------------------------------------------- #
# Companies (all fictional)
# --------------------------------------------------------------------------- #
# Disclosing traders: they publish lists of the cooperatives they buy from.
TRADER_A = "ARBORIA CACAO NEGOCE"   # big disclosing trader
TRADER_B = "BRISEFEVE EXPORT"       # disclosing trader whose disclosures exceed its exports (tests the cap)
# A chocolate maker that discloses cooperatives but does not export itself.
MANUFACTURER = "CHOCOLATERIE ZEPHYR"
# Non-disclosing exporters
NONDISC_1 = "DORADO FEVES"          # also appears in the licensed-buyer list
NONDISC_2 = "ELYSEE TRADING"        # sells some shipments to TRADER_A abroad (tests the importer re-attribution)
NONDISC_3 = "FALAISE AGRO"
# An exporting cooperative. Its customs name has to match a rule in
# countries/cote_divoire/rules/exporting_cooperative_rules.csv, so we use the pattern
# "C A B F", which maps to the acronym "CABF". The cooperative is fictional.
EXPCOOP_CUSTOMS_NAME = "STE COOP C A B F"
EXPCOOP_ACRONYM = "CABF"

IMPORTERS = ["NORDHAVEN COCOA BV", "RIVERSIDE GRINDING GMBH", "PORTLAND CACAO INC",
             "SOLENT FOODS LTD", "VALLEE CHOCOLAT SAS", TRADER_A]
DESTINATIONS = ["NETHERLANDS", "BELGIUM", "GERMANY", "UNITED STATES", "FRANCE",
                "MALAYSIA", "SPAIN", "ESTONIA", "CANADA", "TURKEY"]

# --------------------------------------------------------------------------- #
# Cooperatives and the companies that say they buy from them (supplier map)
# --------------------------------------------------------------------------- #
N_COOPS = 90
certs = ["RAINFOREST ALLIANCE", "FAIRTRADE", "RAINFOREST ALLIANCE, FAIRTRADE",
         "TRADER PROGRAMME", None, None]
coops = []
for i in range(N_COOPS):
    acr = f"SYNCOOP{i:03d}"
    full = f"SOCIETE COOPERATIVE SYNTHETIQUE NUMERO {i:03d}"
    geocode = random.choice(cocoa_codes) if random.random() > 0.05 else None  # a few coops not located
    cert = random.choice(certs)
    coops.append(dict(COOP_ID=i + 1, ACR=acr, FULL=full, GEOCODE=geocode, CERT=cert))
# the exporting cooperative
coops.append(dict(COOP_ID=N_COOPS + 1, ACR=EXPCOOP_ACRONYM,
                  FULL="SOCIETE COOPERATIVE SYNTHETIQUE C A B F",
                  GEOCODE=random.choice(cocoa_codes), CERT="FAIRTRADE"))

# Links: who says they buy from which cooperative, and how many farmers
links = []
flow = 0
def add_link(coop, buyer, trader, num_farmers):
    global flow
    flow += 1
    links.append(dict(coop=coop, BUYER=buyer, TRADER=trader, NUM=num_farmers,
                      FLOW_ID=f"2024-{flow}"))

for c in coops[:N_COOPS]:
    r = random.random()
    farmers = lambda: int(max(20, random.lognormvariate(math.log(450), 0.7)))
    if r < 0.45:
        add_link(c, TRADER_A, TRADER_A, farmers() if random.random() < 0.7 else None)
    elif r < 0.70:
        add_link(c, TRADER_B, TRADER_B, farmers() if random.random() < 0.7 else None)
    elif r < 0.80:
        # cooperative disclosed by both traders
        n = farmers()
        add_link(c, TRADER_A, TRADER_A, n)
        add_link(c, TRADER_B, TRADER_B, None)
    elif r < 0.90:
        # only a chocolate maker discloses this cooperative (not a trader)
        add_link(c, MANUFACTURER, None, farmers())
    else:
        # cooperative listed (e.g. in a certification register) without a buyer
        add_link(c, None, None, None)
# exporting cooperative appears in the map without a buyer link
add_link(coops[-1], None, None, None)

# Written in the standard format (docs/INPUT_DATA.md), like the spreadsheet
# template in supplier_map/templates/.
long_header = ["SUPPLIER_NUMBER", "YEAR", "REGION_CODE", "SUPPLIER_SHORT_NAME", "SUPPLIER_NAME",
               "BUYER", "BUYER_IS_TRADER", "NUMBER_OF_FARMERS", "CERTIFICATIONS", "CERTIFIED",
               "LINK_ID", "DISCLOSED_BY"]
long_rows = []
for l in links:
    c = l["coop"]
    long_rows.append([
        c["COOP_ID"], 2024, c["GEOCODE"], c["ACR"], c["FULL"],
        l["BUYER"], "TRUE" if l["TRADER"] else "FALSE", l["NUM"], c["CERT"],
        None if l["BUYER"] is None else ("TRUE" if c["CERT"] else "FALSE"),
        l["FLOW_ID"], l["BUYER"],
    ])
write_csv("supplier_map/supplier_links_2024.csv", long_header, long_rows, delim=",")

coop_header = ["SUPPLIER_NUMBER", "YEAR", "REGION_CODE", "SUPPLIER_SHORT_NAME", "SUPPLIER_NAME",
               "CERTIFICATIONS", "CERTIFIED"]
coop_rows = []
for c in coops:
    coop_rows.append([c["COOP_ID"], 2024, c["GEOCODE"], c["ACR"], c["FULL"], c["CERT"],
                      "TRUE" if c["CERT"] else "FALSE"])
write_csv("supplier_map/suppliers_2024.csv", coop_header, coop_rows, delim=",")

# --------------------------------------------------------------------------- #
# Licensed buyers (acheteurs agréés)
# --------------------------------------------------------------------------- #
aa_rows = []
for i in range(25):
    code = random.choice(cocoa_codes)
    aa_rows.append([f"REPRESENTANT {i:02d}", f"ACHETEUR SYNTHETIQUE {i:02d}", name_of[code], code])
# one licensed buyer that is also an exporter in customs data
code = random.choice(cocoa_codes)
aa_rows.append(["REPRESENTANT 99", NONDISC_1, name_of[code], code])
write_csv("licensed_buyers/licensed_buyers_2021.csv",
          ["NOM", "DENOMINATION", "ZONE_DACTIVITE", "LVL_4_CODE"], aa_rows)

# --------------------------------------------------------------------------- #
# KIT farm production observations (kg cocoa per farm per year)
# --------------------------------------------------------------------------- #
kit_rows = []
for _ in range(442):
    kg = round(max(0, random.lognormvariate(math.log(900), 0.75)), 1)
    ha = max(0.25, random.lognormvariate(math.log(3), 0.6))
    kit_rows.append([kg, round(kg / ha, 1)])
write_csv("farm_survey/kit_farm_production.csv", ["cocoa_prod_total_kgs", "cocoa_prod_total_kgsha"], kit_rows)

# --------------------------------------------------------------------------- #
# Customs export records (one row per shipment), already preprocessed
# --------------------------------------------------------------------------- #
hs = [("180100", "1801001100", 0.80, 2900), ("180310", "1803100000", 0.06, 6500),
      ("180320", "1803200000", 0.03, 5200), ("180400", "1804000000", 0.06, 7800),
      ("180500", "1805000000", 0.03, 3100), ("180200", "1802000000", 0.02, 300)]
# target bean volumes in tonnes per exporter (roughly)
exporters = [  # (customs name, importer choice, tonnes)
    ("ARBORIA CACAO NEGOCE SA", None, 260000),
    ("ARBORIA CACAO NEGOCE", None, 60000),           # same group, different name variant in customs
    ("BRISEFEVE EXPORT", None, 9000),
    ("DORADO FEVES", None, 40000),
    ("ELYSEE TRADING", TRADER_A, 30000),             # sells to a disclosing trader abroad
    ("ELYSEE TRADING", None, 25000),
    ("FALAISE AGRO", None, 35000),
    (EXPCOOP_CUSTOMS_NAME, None, 4000),
]
trade_rows = []
for name, importer, tonnes in exporters:
    left = tonnes
    while left > 0:
        hs6, hs10, p, usd_t = random.choices(hs, weights=[h[2] for h in hs])[0]
        t = min(left, round(random.uniform(200, 4000), 3))
        left -= t
        imp = importer or random.choice(IMPORTERS[:-1])
        dest = random.choice(DESTINATIONS)
        cif = round(t * usd_t * random.uniform(0.9, 1.1), 2)
        trade_rows.append(["COTE D'IVOIRE", dest, 2024, hs6, hs10, name, imp, round(t, 3), cif])
# small destinations: the quality-check report draws maps for nine named small importing
# countries, so we add a few small shipments to each of them
SMALL_DESTINATIONS = ["SENEGAL", "CHILE", "RUSSIAN FEDERATION", "SYRIAN ARAB REPUBLIC", "ALGERIA",
                      "TAIWAN, PROVINCE OF CHINA", "GREECE", "SAUDI ARABIA", "EGYPT"]
for dest in SMALL_DESTINATIONS:
    for _ in range(2):
        t = round(random.uniform(20, 300), 3)
        trade_rows.append(["COTE D'IVOIRE", dest, 2024, "180100", "1801001100",
                           "ARBORIA CACAO NEGOCE SA", random.choice(IMPORTERS[:-1]), t,
                           round(t * 2900 * random.uniform(0.9, 1.1), 2)])

# a few domestic sales recorded in customs (destination = Côte d'Ivoire)
for _ in range(3):
    trade_rows.append(["COTE D'IVOIRE", "COTE D'IVOIRE", 2024, "180100", "1801001100",
                       "DORADO FEVES", "LOCAL GRINDER SARL", round(random.uniform(1, 50), 3),
                       round(random.uniform(10, 1000), 2)])
write_csv("customs/cocoa_exports_2024.csv",
          ["COUNTRY_OF_ORIGIN", "COUNTRY_OF_DESTINATION", "YEAR", "HS6", "HS_CODE",
           "EXPORTER", "BUYER", "NET_WEIGHT_TON", "CIF_USD"], trade_rows)

# --------------------------------------------------------------------------- #
# Extra inputs used only by the optional quality-check report
# --------------------------------------------------------------------------- #
prod_rows = [[c, round(random.uniform(5e6, 9e7))] for c in cocoa_codes]
write_csv("quality_check_data/eth_cocoa_production_pg_2019_oct22.csv",
          ["LVL_4_CODE", "eth_production_2019_kg"], prod_rows)

area_rows = [[c, round(random.uniform(5e3, 1.5e5), 1)] for c in cocoa_codes]
write_csv("quality_check_data/eth_area_under_cocoa_ha_civ_oct22.csv", ["LVL_4_CODE", "sum"], area_rows, delim=",")

# ZDC file: the real file has a title line above the header (read with skip = 1)
zdc_path = os.path.join(OUT, "quality_check_data", "ZDC_collection_2020.csv")
with open(zdc_path, "w", newline="", encoding="utf-8") as f:
    f.write("Synthetic zero-deforestation-commitment table\n")
    w = csv.writer(f, delimiter=";")
    w.writerow(["Commodity", "Country", "Year", "Exporter", "ZDC"])
    for ex, z in [(TRADER_A, "Company commitment"), (TRADER_B, "None"), (NONDISC_1, "None"),
                  (NONDISC_2, "None"), (NONDISC_3, "Company commitment")]:
        w.writerow(["Cocoa", "Cote d’Ivoire", 2019, ex, z])
print("wrote", os.path.relpath(zdc_path, HERE))

# UN Comtrade-style export totals (country = partner; World = all partners)
ct_rows = []
totals = {}
for r in trade_rows:
    if r[3] == "180200":
        continue
    for partner in (r[1], "World"):
        k = (r[3], partner)
        q, v = totals.get(k, (0.0, 0.0))
        totals[k] = (q + r[7] * 1000, v + r[8])
for (hs6, partner), (kg, usd) in sorted(totals.items()):
    if partner == "COTE D'IVOIRE":
        continue
    partner_desc = {"UNITED STATES": "USA"}.get(partner, partner.title())
    ct_rows.append([2024, hs6, partner_desc, round(kg * random.uniform(0.9, 1.1)), 0,
                    round(usd * random.uniform(0.9, 1.1), 2)])
write_csv("quality_check_data/comtrade_civ_cocoa_exports_2019_2024.csv",
          ["refYear", "cmdCode", "partnerDesc", "qty", "altQty", "cifvalue"], ct_rows, delim=",")


# --------------------------------------------------------------------------- #
# Spatial metrics (made up), in the format written by
# deforestation_metrics/reshape_earth_engine_exports.py, plus regional cocoa
# production and area (GEE sections B and C). Used by the deforestation-
# exposure step. Generated last so the files above do not change.
# --------------------------------------------------------------------------- #
def region_id(code):         # "CI-3.1.2_1" -> "CI-030102"
    prefix, rest = code.split('-')
    return prefix + '-' + ''.join(n.zfill(2) for n in rest.split('_')[0].split('.'))

met_rows, prod_rows2, area_rows2 = [], [], []
for c in cocoa_codes:
    ha = round(random.uniform(5e3, 1.5e5), 1)
    area_rows2.append([region_id(c), ha])
    for y in range(2019, 2025):
        tn = round(ha * random.uniform(0.35, 0.55), 1)
        prod_rows2.append([region_id(c), y, tn])
        dd15 = round(ha * random.uniform(0.05, 0.35), 2)
        dd1 = round(dd15 / random.uniform(8, 20), 2)
        g15, g1 = round(dd15 * 0.6 * 450, 1), round(dd1 * 0.6 * 450, 1)   # emissions: deforested part only
        met_rows.append([region_id(c), y, dd15, dd1, g15, g1, round(max(0, g15 - dd15 * 0.6 * 84.41), 1),
                         round(max(0, g1 - dd1 * 0.6 * 84.41), 1)])
write_csv("deforestation_metrics/cocoa_deforestation_by_region.csv",
          ["REGION_ID", "YEAR", "COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL",
           "COCOA_DEFORESTATION_AND_DEGRADATION_ANNUAL", "COCOA_GROSS_EMISSIONS_15_YEARS_TOTAL",
           "COCOA_GROSS_EMISSIONS_ANNUAL", "COCOA_NET_EMISSIONS_15_YEARS_TOTAL", "COCOA_NET_EMISSIONS_ANNUAL"],
          met_rows, delim=",")
write_csv("deforestation_metrics/cocoa_production_by_region.csv", ["REGION_ID", "YEAR", "COCOA_TONNES"], prod_rows2, delim=",")
write_csv("deforestation_metrics/cocoa_area_by_region.csv", ["REGION_ID", "COCOA_HA"], area_rows2, delim=",")
# Optional extras for the exposure step: an attribute per region (here a
# made-up ecoregion label) and the exporters' zero-deforestation commitments.
eco = ["FOREST ZONE", "FOREST-SAVANNA TRANSITION"]
write_csv("deforestation_metrics/region_attributes.csv", ["REGION_ID", "ECOREGION"],
          [[region_id(c), eco[int(c.split("-")[1].split(".")[0]) % 2]] for c in cocoa_codes], delim=",")
write_csv("deforestation_metrics/company_commitments.csv",
          ["EXPORTER_GROUP", "HAS_COMMITMENT", "COMMITMENT_TYPE", "START_YEAR", "END_YEAR"],
          [[TRADER_A, "TRUE", "ZERO DEFORESTATION", 2018, None],
           [TRADER_B, "TRUE", "ZERO GROSS DEFORESTATION", 2025, None],
           [NONDISC_1, "FALSE", None, None, None]], delim=",")
print("\nAll files above are synthetic. Do not interpret model results built from them.")
