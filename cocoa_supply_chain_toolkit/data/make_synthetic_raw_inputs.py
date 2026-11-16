"""
Generate SYNTHETIC RAW inputs, so that the worked examples that start from raw
data can be run end to end:

  supplier_map/build_supplier_map_cote_divoire_2024.py   (steps 1-5)
  input_preparation/trade/clean_customs_cote_divoire_2024.R
  input_preparation/farm_production/farm_production_from_kit_survey.Rmd
  input_preparation/licensed_buyers/locate_licensed_buyers_cote_divoire.R
  deforestation_metrics/reshape_earth_engine_exports.py

Everything written here is MADE UP. Files are named and laid out like the real
ones (company disclosures in each company's own format, raw customs records,
the KIT survey file, the regulator's lists, Earth Engine exports), but the
cooperatives, numbers and coordinates are fictional, and the companies'
"disclosures" are invented: they are not what those companies published.

The results land in the same folder (data/synthetic_raw_inputs/), so the
model's ready-made example inputs in data/synthetic_cote_divoire/ are never
overwritten.

Usage (from the toolkit's top folder):
    python3 data/make_synthetic_raw_inputs.py
Needs pandas, geopandas and openpyxl (see requirements.txt); the KIT file is
written by R (Rscript must be available).
"""
import json
import os
import random
import shutil
import subprocess

import geopandas as gpd
import numpy as np
import pandas as pd

random.seed(11)
rng = np.random.default_rng(11)
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "synthetic_raw_inputs")
SRC = os.path.join(HERE, "synthetic_cote_divoire")
NOTE = "SYNTHETIC - made-up data for the toolkit's examples; not a real disclosure"


def path(*parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def written(p):
    print("wrote", os.path.relpath(p, HERE))


# --------------------------------------------------------------------------- #
# Regions: the open-licensed department boundaries, copied from the example
# --------------------------------------------------------------------------- #
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT)
for f in ("departments.geojson", "SOURCE.md"):
    shutil.copy(os.path.join(SRC, "regions", f), path("regions", f))
depts = gpd.read_file(os.path.join(SRC, "regions", "departments.geojson"))
pts = depts.to_crs(32630).representative_point().to_crs(4326)
depts["LAT"], depts["LON"] = pts.y.round(5), pts.x.round(5)
cocoa = depts.sample(30, random_state=3).reset_index(drop=True)

# --------------------------------------------------------------------------- #
# A pool of fictional cooperatives (some already in last year's map)
# --------------------------------------------------------------------------- #
syll = ["KA", "BO", "DI", "GNA", "YA", "SO", "TI", "ZO", "ME", "LO", "PA", "NI", "WE", "FA"]
coops = []
for i in range(90):
    d = cocoa.iloc[i % len(cocoa)]
    word = "".join(random.sample(syll, 2))
    short = random.choice(["SCOOPS ", "COOP-CA ", "SOCA", "ECA", "CA"]) + word
    coops.append(dict(
        SHORT=short.strip(),
        FULL=f"SOCIETE COOPERATIVE AGRICOLE {word} DE {d.LVL_4_NAME}",
        DEPT=d.LVL_4_NAME, CODE=d.LVL_4_CODE,
        LAT=round(float(d.LAT + rng.normal(0, 0.03)), 5), LON=round(float(d.LON + rng.normal(0, 0.03)), 5),
        FARMERS=int(rng.lognormal(np.log(500), 0.6)),
        IN_2023=i < 60))


def pick(n):
    return random.sample(coops, n)


DISC = path("supplier_map", "company_disclosures_2024", "x")[:-2]

# --- scraped maps -----------------------------------------------------------
# Blommer: a Python list of records; fields 6-11 are country, trader, name,
# area, latitude, longitude
rows = [[0, 0, 0, 0, 0, 0, "IVORY COAST", "BLOMMER", c["SHORT"], c["DEPT"], c["LAT"], c["LON"]] for c in pick(8)]
p = os.path.join(DISC, "scraped_map", "blommer_map_scraped.txt"); os.makedirs(os.path.dirname(p), exist_ok=True)
open(p, "w").write(repr(rows)); written(p)

# Touton: a JSON-like dump of a web map, plus the same list saved as CSV
tou = pick(8)
blob = [[], None, [[[], None, 1, 1, [[None, [c["LAT"], c["LON"]]]], [[[c["SHORT"]]]]] for c in tou]]
p = os.path.join(DISC, "scraped_map", "touton_map_scraped.txt"); open(p, "w").write(json.dumps(blob)); written(p)
p = os.path.join(DISC, "scraped_map", "touton_map_as_csv.csv")
pd.DataFrame({"Cooperative Name": [c["SHORT"] for c in tou], "Location": [c["DEPT"] for c in tou],
              "Latitude": [c["LAT"] for c in tou], "Longitude": [c["LON"] for c in tou],
              "Number of Farmers": [c["FARMERS"] for c in tou]}).to_csv(p, index=False); written(p)

# Cargill: a GeoJSON of cooperatives (shapefile-style truncated field names)
car = pick(12)
g = gpd.GeoDataFrame({
    "objectid": range(1, 13), "coop_name": [c["SHORT"] for c in car],
    "gps_lat": [c["LAT"] for c in car], "gps_long": [c["LON"] for c in car],
    "country": "Côte d'Ivoire", "certificat": random.choices(["Rainforest Alliance", "Fairtrade", None], k=12),
    "f__certifi": rng.integers(40, 100, 12), "location_t": "Cooperative",
    "year_joined": rng.integers(2015, 2024, 12), "year_joine": rng.integers(2015, 2024, 12)},
    geometry=gpd.points_from_xy([c["LON"] for c in car], [c["LAT"] for c in car]), crs=4326)
p = os.path.join(DISC, "scraped_map", "cargill_coops_2324.geojson"); g.to_file(p, driver="GeoJSON"); written(p)

# Whittaker's: one line per village, key="value" pairs (Ghana sourcing; the
# script keeps three named operations)
p = os.path.join(DISC, "scraped_map", "whittakers_scraped_map.txt")
with open(p, "w") as f:
    for op in ["Asankrangwa", "Tarkwa-Huni", "Assin"]:
        for v in range(3):
            f.write(f'<marker op="{op}" village="Village{v}{op[:3]}" growers="{rng.integers(20, 90)}" harvest="{rng.integers(1, 9)},{rng.integers(100, 999)}" />\n')
written(p)

# --- tables extracted from PDFs (Tabula) -------------------------------------
tab = os.path.join(DISC, "tabula_outputs"); os.makedirs(os.path.join(tab, "ecom"), exist_ok=True)
c = pick(10)
pd.DataFrame({"No": range(1, 11), "Farmer Group": [x["SHORT"] for x in c], "Location": [x["DEPT"] for x in c]}) \
  .to_csv(p := os.path.join(tab, "tabula-cote-d-ivoire-ofi-sustainable-cocoa-suppliers-2023-and-2024.csv"), index=False); written(p)
c = pick(8)
pd.DataFrame({"Cooperative Name": [x["SHORT"] for x in c], "Region": [x["DEPT"] for x in c],
              "Full Name": [x["FULL"] for x in c]}).to_csv(p := os.path.join(tab, "ecom", "ecom_CIV.csv"), index=False); written(p)
c = pick(8)
pd.DataFrame({"Country": "Ivory Coast", "Supplier Name": [x["SHORT"] for x in c],
              "Latitude": [x["LAT"] for x in c], "Longitude": [x["LON"] for x in c]}) \
  .to_csv(p := os.path.join(tab, "tabula-etg 2024.csv"), index=False); written(p)
c = pick(6)
pd.DataFrame({"LOCATION ORIGIN": "Côte d'Ivoire", "FARMER GROUP": [x["SHORT"] for x in c],
              "FULL NAME": [x["FULL"] for x in c], "MAIN CITY": [x["DEPT"] for x in c]}) \
  .to_csv(p := os.path.join(tab, "tabula-ferrero-cocoa-suppliers-list-23-24.csv"), index=False); written(p)
mars = pick(10)
pd.DataFrame({"INDEX": range(10), "COUNTRY": "Côte d'Ivoire", "DISCL_SUPPLIER_ABRVNAME": [x["SHORT"] for x in mars],
              "DISCL_TRADER_NAME": random.choices(["BARRY CALLEBAUT", "CARGILL", "OFI"], k=10)}) \
  .to_csv(p := os.path.join(tab, "tabula-2023 T2 MARS COCOA SUPPLY CHAIN DISCLOSURE -Jan 2024 FINAL-3.csv"), index=False); written(p)
c = pick(6)
pd.DataFrame({"Country of Origin": "Côte d'Ivoire", "Intermediary Supplier": [x["SHORT"] for x in c],
              "Intermediary Supplier Location (Country)": "Côte d'Ivoire",
              "Direct Supplier": random.choices(["CARGILL", "OFI", "ECOM"], k=6), "Type": "Cooperative"}) \
  .to_csv(p := os.path.join(tab, "tabula-nestle_2025_responsible-sourcing-disclosure-cocoa.csv"), index=False); written(p)

# --- spreadsheets ---------------------------------------------------------------
xl = os.path.join(DISC, "excel"); os.makedirs(xl, exist_ok=True)
c = pick(5)
pd.DataFrame({"N": range(1, 6), "SUPPLIER": [x["SHORT"] for x in c], "LOCATION": [x["DEPT"] for x in c],
              "COMPANY": "CEMOI VIA TRANSPARANCE COCOA", "COUNTRY": "Ivory Coast", "DISCL_YEAR": 2024}) \
  .to_csv(p := os.path.join(xl, "2024_transparance.csv"), index=False); written(p)
c = pick(6)
pd.DataFrame({"Country": ["Côte d'Ivoire"] * 5 + ["Ghana"], "Tier 2 Supplier": random.choices(["BARRY CALLEBAUT", "CARGILL"], k=6),
              "Tier 1 Supplier": "LINDT SPRUNGLI", "Farmer Group/District": [x["SHORT"] for x in c],
              "Location": [x["DEPT"] for x in c], "COMPANY": "LINDT SPRUNGLI", "DISCL_YEAR": 2024}) \
  .to_csv(p := os.path.join(xl, "2024_lindt_sprungli.csv"), index=False); written(p)
c = pick(4)
pd.DataFrame({"COMPANY": "ALTER ECO", "COUNTRY": "Côte d'Ivoire", "DISCL_SUPPLIER_ABRVNAME": [x["SHORT"] for x in c],
              "DISCL_YEAR": 2024}).to_excel(p := os.path.join(xl, "alter_eco_sourcing_2018-2024.xlsx"), index=False); written(p)

# Mars' update for 2024 (short names only; some already in the 2023 list)
upd = mars[:6] + pick(4)
pd.DataFrame({"DISCL_COUNTRY_NAME": "IVORY_COAST", "DISCL_SUPPLIER_ABRVNAME": [x["SHORT"] for x in upd],
              "DISCL_YEAR": 2024.0, "COMPANY": "MARS"}) \
  .to_csv(p := os.path.join(DISC, "mars_2024_update.csv"), index=False); written(p)

# Ritter Sport's list was typed in by hand into the step-1 folder. It also
# carries the odd column names that some other real files have, so that every
# clean-up rule of step 2 has something to do.
c = pick(5)
p = path("supplier_map", "work", "step1_by_company", "2024_ritter_sport.csv")
pd.DataFrame({"COMPANY": "ALFRED RITTER", "TRADER": "KRUGER", "SUPPLIER_ABRVNAME": [x["SHORT"] for x in c],
              "SUPPLIER_FULLNAME": [x["FULL"] for x in c], "DISCL_SUPPLIER_NAME": None, "LOCALITY_NAME": [x["DEPT"] for x in c],
              "DISTRICT_NAME": None, "DISTRICT_GEOCODE": None, "COUNTRY_NAME": "IVORY COAST", "DISCL_COUNTRY": None,
              " DISCL_YEAR": 2024, "YEAR": None, "LATITUDE": [x["LAT"] for x in c], "LONGITUDE": [x["LON"] for x in c],
              "TYPE": "Cooperative", "INDEX": range(5),
              "DISCL_NUMBER_FARMERS.1": [x["FARMERS"] for x in c], "DISCL_VOLUMES.1": None, "DISCL_VOLUMES_UNIT.1": None,
              "DISCL_CERTIFICATION_NAME.1": "Fairtrade", "DISCL_CERTIFICATION_PCT.1": None,
              "CAM_BUYERS": None, "IS_CAM_V3": False, "IS_JRC": False, "JRC_BUYER_ID": None}).to_csv(p, index=False); written(p)

# --------------------------------------------------------------------------- #
# Last year's map and disclosures (2023), in last year's column layout
# --------------------------------------------------------------------------- #
traders = ["BARRY CALLEBAUT", "CARGILL", "OLAM", "ECOM", "TOUTON", "ETC GROUP", "CEMOI", "SUCDEN"]
old = [c for c in coops if c["IN_2023"]]
links23 = []
for i, c in enumerate(old):
    for t in random.sample(traders, random.choice([1, 1, 2])):
        links23.append(dict(c=c, BUYER=t, TRADER_NAME=t, N=int(c["FARMERS"] * rng.uniform(0.6, 1.2))))
coop_cols = ["COOP_ID", "YEAR", "SUPPLIER_ABRVNAME", "SUPPLIER_FULLNAME", "LATITUDE", "LONGITUDE", "DISTRICT_NAME",
             "DISTRICT_GEOCODE", "DISCLOSURE_SOURCES", "TRADER_NAMES", "CERTIFIED", "CERTIFICATIONS",
             "TOTAL_FARMERS_NONTRADER", "TOTAL_FARMERS_TRADER", "TOTAL_FARMERS", "DISCL_COUNTRY_NAME", "DISCL_AREA_NAME",
             "DISCL_SUPPLIER_ABRVNAME", "DISCL_SUPPLIER_FULLNAME", "DISCL_SUPPLIER_TYPE", "DISCL_LONGITUDE",
             "DISCL_LATITUDE", "DISCL_VOLUMES", "DISCL_VOLUMES_UNIT", "DISCL_CERTIFICATION_NAME",
             "DISCL_CERTIFICATION_PCT", "SIMPLIF_ABRVNAME", "CCTN_COOP_ID", "IS_ALL_CAM_V3", "IS_ANY_CAM_V3",
             "NB_FARMERS_COMPANY_YEAR", "!NOT_RFA", "unique_rfa_link", "TOTAL_FARMERS_RFA", "LVL_4_NAME",
             "REPEATED_FROM_PAST_YEAR"]
rows = []
for i, c in enumerate(old, 1):
    ts = sorted({l["BUYER"] for l in links23 if l["c"] is c})
    rows.append({"COOP_ID": i, "YEAR": 2023, "SUPPLIER_ABRVNAME": c["SHORT"], "SUPPLIER_FULLNAME": c["FULL"],
                 "LATITUDE": c["LAT"], "LONGITUDE": c["LON"], "DISTRICT_NAME": c["DEPT"], "DISTRICT_GEOCODE": c["CODE"],
                 "DISCLOSURE_SOURCES": " + ".join(ts), "TRADER_NAMES": " + ".join(ts), "CERTIFIED": False,
                 "TOTAL_FARMERS": c["FARMERS"], "DISCL_COUNTRY_NAME": "IVORY_COAST", "DISCL_AREA_NAME": c["DEPT"],
                 "DISCL_SUPPLIER_ABRVNAME": c["SHORT"], "DISCL_SUPPLIER_FULLNAME": c["FULL"],
                 "DISCL_SUPPLIER_TYPE": "COOPERATIVE", "DISCL_LONGITUDE": c["LON"], "DISCL_LATITUDE": c["LAT"],
                 "IS_ALL_CAM_V3": False, "IS_ANY_CAM_V3": False, "LVL_4_NAME": c["DEPT"],
                 "REPEATED_FROM_PAST_YEAR": False})
pd.DataFrame(rows, columns=coop_cols).to_csv(p := path("supplier_map", "last_year", "cooperatives_2023.csv"),
                                             sep=";", index=False, na_rep="NA"); written(p)
link_cols = ["FLOW_ID", "COOP_ID", "YEAR", "SUPPLIER_ABRVNAME", "SUPPLIER_FULLNAME", "LATITUDE", "LONGITUDE",
             "DISTRICT_NAME", "DISTRICT_GEOCODE", "BUYER", "DISCLOSURE_SOURCE", "TRADER_NAME", "CERTIFICATIONS",
             "NUM_FARMERS", "NUM_FARMERS_EXTRAPOLATED", "DISCL_NUMBER_FARMERS", "DISCL_COUNTRY_NAME",
             "DISCL_SUPPLIER_ABRVNAME", "DISCL_SUPPLIER_FULLNAME", "CERTIFIED", "IS_TRADER", "LVL_4_NAME",
             "REPEATED_FROM_PAST_YEAR"]
rows = []
for k, l in enumerate(links23, 1):
    c = l["c"]
    rows.append({"FLOW_ID": f"2023-{k}", "COOP_ID": old.index(c) + 1, "YEAR": 2023, "SUPPLIER_ABRVNAME": c["SHORT"],
                 "SUPPLIER_FULLNAME": c["FULL"], "LATITUDE": c["LAT"], "LONGITUDE": c["LON"],
                 "DISTRICT_NAME": c["DEPT"], "DISTRICT_GEOCODE": c["CODE"], "BUYER": l["BUYER"],
                 "DISCLOSURE_SOURCE": l["BUYER"], "TRADER_NAME": l["TRADER_NAME"], "NUM_FARMERS": l["N"],
                 "NUM_FARMERS_EXTRAPOLATED": l["N"], "DISCL_NUMBER_FARMERS": l["N"], "DISCL_COUNTRY_NAME": "IVORY_COAST",
                 "DISCL_SUPPLIER_ABRVNAME": c["SHORT"], "DISCL_SUPPLIER_FULLNAME": c["FULL"], "CERTIFIED": False,
                 "IS_TRADER": True, "LVL_4_NAME": c["DEPT"], "REPEATED_FROM_PAST_YEAR": False})
pd.DataFrame(rows, columns=link_cols).to_csv(p := path("supplier_map", "last_year", "links_2023.csv"),
                                             sep=";", index=False, na_rep="NA"); written(p)
disc_cols = ["COMPANY", "DISCL_COUNTRY_NAME", "DISCL_TRADER_NAME", "DISCL_AREA_NAME", "DISCL_SUPPLIER_ABRVNAME",
             "DISCL_SUPPLIER_FULLNAME", "DISCL_SUPPLIER_TYPE", "DISCL_LONGITUDE", "DISCL_LATITUDE", "DISCL_YEAR",
             "DISCL_NUMBER_FARMERS", "DISCL_VOLUMES", "DISCL_VOLUMES_UNIT", "DISCL_CERTIFICATION_NAME",
             "DISCL_CERTIFICATION_PCT", "DISTRICT_NAME", "DISTRICT_GEOCODE", "LOCALITY_NAME", "TRADER_NAME",
             "CAM_BUYERS", "IS_CAM_V3", "IS_JRC", "JRC_BUYER_ID"]
rows = [{"COMPANY": l["BUYER"], "DISCL_COUNTRY_NAME": "IVORY COAST", "DISCL_TRADER_NAME": l["TRADER_NAME"],
         "DISCL_AREA_NAME": l["c"]["DEPT"], "DISCL_SUPPLIER_ABRVNAME": l["c"]["SHORT"],
         "DISCL_SUPPLIER_FULLNAME": l["c"]["FULL"], "DISCL_SUPPLIER_TYPE": "COOPERATIVE",
         "DISCL_LONGITUDE": l["c"]["LON"], "DISCL_LATITUDE": l["c"]["LAT"], "DISCL_YEAR": 2023,
         "DISCL_NUMBER_FARMERS": l["N"], "DISTRICT_NAME": l["c"]["DEPT"], "DISTRICT_GEOCODE": l["c"]["CODE"],
         "TRADER_NAME": l["TRADER_NAME"], "IS_CAM_V3": False, "IS_JRC": False} for l in links23]
pd.DataFrame(rows, columns=disc_cols).to_csv(p := path("supplier_map", "last_year", "company_disclosures_2023.csv"),
                                             sep=";", index=False); written(p)
# Mark every made-up disclosure as synthetic in its file name. The supplier-map
# script reads SYNTHETIC_<name> when the real file <name> is not there.
for folder in (DISC, path("supplier_map", "work", "step1_by_company", "x")[:-2]):
    for root, _, files in os.walk(folder):
        for f in files:
            os.rename(os.path.join(root, f), os.path.join(root, "SYNTHETIC_" + f))
open(path("supplier_map", "README.txt"), "w").write(
    NOTE + ".\nEvery file whose name starts with SYNTHETIC_ is invented. The company names\n"
    "only show which real disclosure each file stands in for; the cooperatives,\n"
    "locations and figures are made up and are not what those companies published.\n"
    "Put the real files here under their original names (without SYNTHETIC_) and\n"
    "the supplier-map script will use them instead.\n")

# --------------------------------------------------------------------------- #
# Raw customs records (for input_preparation/trade/), built from the ready-made
# example customs table so the two agree
# --------------------------------------------------------------------------- #
ex = pd.read_csv(os.path.join(SRC, "customs", "cocoa_exports_2024.csv"), sep=";", dtype={"HS_CODE": str, "HS6": str})
french = {"NETHERLANDS": "Pays-bas", "UNITED STATES": "Etats-Unis", "GREECE": "Grece",
          "SAUDI ARABIA": "Arabie Saoudite", "RUSSIAN FEDERATION": "Russie, Federation de",
          "SYRIAN ARAB REPUBLIC": "Syrienne, Republique arabe", "TAIWAN, PROVINCE OF CHINA": "Taiwan"}
desc = {"1801": "FEVES DE CACAO", "1802": "COQUES DE CACAO", "1803": "PATE DE CACAO", "1804": "BEURRE DE CACAO", "1805": "POUDRE DE CACAO"}
units = {"1801": "SAC EN JUTE", "1802": "SAC EN JUTE", "1803": "CARTON", "1804": "CARTON", "1805": "SAC (SACK)"}
ex = ex[ex.COUNTRY_OF_DESTINATION != "COTE D'IVOIRE"]
raw = pd.DataFrame({
    "DATE": [f"{rng.integers(1, 28):02d}/{rng.integers(1, 13):02d}/2024" for _ in range(len(ex))],
    "YEAR": "2024",
    "EXPORTER": ex.EXPORTER.values,
    "IMMIMP": [f"{rng.integers(1000000, 9999999)}X" for _ in range(len(ex))],
    "SUPPLIER": ex.BUYER.values,
    "ORIGINE": "COTE D'IVOIRE",
    "DESTINATION": [french.get(d, d.title()) for d in ex.COUNTRY_OF_DESTINATION],
    "SH": ex.HS_CODE.values,
    "COMMERCIAL PRODUCT DESC": [desc[h[:4]] for h in ex.HS_CODE],
    "NET WEIGHT": (ex.NET_WEIGHT_TON * 1000).round(1).values,
    "GROSS WEIGHT": (ex.NET_WEIGHT_TON * 1010).round(1).values,
    "QUANTITY": (ex.NET_WEIGHT_TON * 1000 / 65).round(0).values,
    "UNIT": [units[h[:4]] for h in ex.HS_CODE],
    "CIF VALUE": ex.CIF_USD.values,
    "FOB VALUE": (ex.CIF_USD * 0.95).round(2).values,
    "TRANSPORT MODE": "MARITIME",
})
p = path("customs", "raw", "CIV_2024_all_one_sheet.xlsx"); raw.to_excel(p, index=False); written(p)
iso = {"NL": "NETHERLANDS", "US": "UNITED STATES", "BE": "BELGIUM", "TR": "TURKEY", "FR": "FRANCE", "CA": "CANADA",
       "MY": "MALAYSIA", "ES": "SPAIN", "DE": "GERMANY", "EE": "ESTONIA", "SN": "SENEGAL", "CL": "CHILE",
       "RU": "RUSSIAN FEDERATION", "SY": "SYRIAN ARAB REPUBLIC", "DZ": "ALGERIA", "TW": "TAIWAN, PROVINCE OF CHINA",
       "GR": "GREECE", "SA": "SAUDI ARABIA", "EG": "EGYPT", "CI": "COTE D'IVOIRE"}
pd.DataFrame({"ISO2": list(iso), "COUNTRY": list(iso.values())}) \
  .to_csv(p := path("customs", "ISO2_ENGLISH_COUNTRY_NAMES.csv"), sep=";", index=False); written(p)

# --------------------------------------------------------------------------- #
# Farm survey (for input_preparation/farm_production/): an .RData file shaped
# like the KIT survey's (country 1 = Ghana, 2 = Côte d'Ivoire)
# --------------------------------------------------------------------------- #
n = 600
land = rng.lognormal(np.log(3), 0.6, n).round(2)
farm = pd.DataFrame({
    "country": rng.choice([1, 2], n, p=[0.3, 0.7]),
    "sub_region": rng.integers(1, 8, n),
    "latitude": rng.uniform(5.2, 7.5, n).round(4), "longitude": rng.uniform(-7.5, -3.5, n).round(4),
    "cocoa_land_used_ha": land, "cocoa_land_used_morethan5_ha": (land * rng.uniform(0.6, 1, n)).round(2),
    "cocoa_prod_total_kgs": rng.lognormal(np.log(900), 0.75, n).round(1)})
farm["cocoa_prod_total_kgsha"] = (farm.cocoa_prod_total_kgs / farm.cocoa_land_used_morethan5_ha).round(1)
farm.loc[rng.random(n) < 0.3, ["cocoa_prod_total_kgs", "cocoa_prod_total_kgsha"]] = np.nan   # not every farm answered
tmp = path("farm_survey", "kit_like.csv"); farm.to_csv(tmp, index=False)
rdata = path("farm_survey", "0 Cocoa_Livelihoods_export_Dataverse.RData")
subprocess.run(["Rscript", "-e", f"table <- read.csv('{tmp}'); save(table, file = '{rdata}')"], check=True)
os.remove(tmp); written(rdata)

# --------------------------------------------------------------------------- #
# The regulator's lists of licensed buyers (for input_preparation/licensed_buyers/),
# one file per campaign, each in its own layout
# --------------------------------------------------------------------------- #
lb = os.path.join(OUT, "licensed_buyers"); os.makedirs(lb, exist_ok=True)
names = [f"ACHETEUR SYNTHETIQUE {i:02d}" for i in range(20)]
reps = [f"REPRESENTANT {i:02d}" for i in range(20)]
zones = [random.choice(cocoa.LVL_4_NAME.tolist()) for _ in range(20)]
pd.DataFrame({"NOM": reps, "DENOMINATION": names, "ZONE_DACTIVITE": zones}) \
  .to_csv(p := os.path.join(lb, "ACHATEURS_AGREES.csv"), index=False); written(p)
pd.DataFrame({"NOM & PRENOMS": reps, "DENOMINATION": names, "DR": "DR SYNTHETIQUE",
              "ZONE D'ACTIVITE": zones, "CODE DR": 1, "CODE": [f"C{i:03d}" for i in range(20)],
              "CONTACT": "00 00 00 00", "TYPE": "ACHETEUR"}) \
  .to_excel(p := os.path.join(lb, "2020_ACHATEURS_AGREES.xlsx"), index=False); written(p)
# (the header "NÂ°" is how the column "N°" of the real files is read)
pd.DataFrame({"NÂ°": range(1, 21), "REPRESENTANT": reps, "DENOMINATION": names, "DEPARTEMENT": zones}) \
  .to_excel(p := os.path.join(lb, "ACHETEURS_AGREES_CAMPAGNE_2020_2021.xlsx"), index=False); written(p)
pd.DataFrame({"NÂ°": range(1, 21), "NOM & PRENOMS": reps, "DENOMINATION": names, "ZONE D'ACTIVITE": zones,
              "Field5": None, "Field6": None}) \
  .to_excel(p := os.path.join(lb, "PREMIERE_LISTE_ACHETEURS_AGREES_CAMPAGNE_2018_2019.xlsx"), index=False); written(p)

# --------------------------------------------------------------------------- #
# Earth Engine exports (for deforestation_metrics/reshape_earth_engine_exports.py):
# one CSV per export of cocoa_deforestation_metrics.js, one row per department
# --------------------------------------------------------------------------- #
ee_dir = os.path.join(OUT, "earth_engine_exports"); os.makedirs(ee_dir, exist_ok=True)
props = depts[["LVL_1_CODE", "LVL_1_NAME", "LVL_2_CODE", "LVL_2_NAME", "LVL_3_CODE", "LVL_3_NAME",
               "LVL_4_CODE", "LVL_4_NAME"]]
bands = {
    "eth2021_cocoa_tmfloss_annual_ha": [f"cd_1yr_tmf_{t}_{y}" for y in range(2014, 2025) for t in ("loss", "def", "deg")],
    "eth2021_cocoa_tmfloss_total_15yr": [f"cd_15yr_tmf_{t}_{y}" for y in range(2014, 2025) for t in ("loss", "def", "deg")],
    "ghg_cd_gross_1yr": [f"ghg_cd_1yr_gross_{y}" for y in range(2014, 2025)],
    "ghg_cd_gross_15yr": [f"ghg_cd_15yr_gross_{y}" for y in range(2014, 2025)],
    "ghg_cd_net_1yr": [f"ghg_cd_1yr_net_{y}" for y in range(2014, 2025)],
    "ghg_cd_net_15yr": [f"ghg_cd_15yr_net_{y}" for y in range(2014, 2025)],
    "ghg_territorial_gross_1yr": [f"ghg_uTMF_def_1yr_gross_{y}" for y in range(2000, 2025)],
    "territorial_tmfloss_annual_ha": [f"uTMF_1yr_{t}_{y}" for y in range(2000, 2025) for t in ("lost_by", "defo_by", "degr_by")],
    "undisturbed_tmf_yearly": [f"uTMF_remaining{y}" for y in range(2000, 2025)],
}
for name, cols in bands.items():
    df = props.copy()
    df.insert(0, "system:index", [f"{i:04d}" for i in range(len(df))])
    for c in cols:
        df[c] = rng.uniform(0, 2000 if "15yr" in c or "remaining" in c else 300, len(df)).round(3)
    df[".geo"] = "{}"
    df.to_csv(p := os.path.join(ee_dir, f"{name}_ci.csv"), index=False); written(p)
area = props.copy(); area["sum"] = rng.uniform(1000, 150000, len(area)).round(1)
area.to_csv(p := os.path.join(ee_dir, "cocoa_area_ci_v1.csv"), index=False); written(p)
prod = pd.DataFrame({"REGION_ID": props.LVL_4_CODE})
for y in range(2019, 2025):
    prod[f"production_{y}"] = (area["sum"] * rng.uniform(0.35, 0.55, len(area))).round(1)
prod.to_csv(p := os.path.join(ee_dir, "cocoa_production_ci_v1.csv"), index=False); written(p)

print("\nAll files above are synthetic.")
