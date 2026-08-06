#!/usr/bin/env python3
"""
Trase Earth - Cooperative Disclosure Integrator (Multi-Year Version)

DESCRIPTION:
This script allows users to take their own messy cooperative disclosure data (CSV), 
clean it, and merge it with the official base GeoJSON dataset downloaded from Trase Earth.
It matches cooperatives using text normalization and fuzzy matching on BOTH Name and Year.
It updates existing cooperatives, rolls forward existing cooperatives for new years, 
and creates brand new spatial features for unknown cooperatives using department polygons.

HOW TO RUN:
   Open your terminal/command prompt and run the script:
       poetry run python update_trase_coops.py --default-year 2024
"""

import pandas as pd
import numpy as np
import geopandas as gpd
import re
import unicodedata
import argparse
from rapidfuzz import fuzz, process
import warnings
from pathlib import Path
import sys

warnings.simplefilter(action="ignore", category=FutureWarning)


# =============================================================================
# GLOBAL HELPER FUNCTIONS
# =============================================================================
def remove_accents(text):
    if pd.isna(text) or not isinstance(text, str):
        return text
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ASCII", "ignore")
        .decode("ASCII")
        .upper()
        .strip()
    )


def clean_coop_name(col_name):
    if not isinstance(col_name, str):
        return col_name
    c = remove_accents(col_name)
    c = re.sub(r"\.|[(]|[)]| WAREHOUSE$", "", c)
    c = re.sub(r"\n|_|/|-", " ", c)
    pattern = r"\bCOOP CA\b|\bSAND BOX\b|\bCOOP\b|\bWAREHOUSE\b|\bAVEC CONSEIL D'ADMINISTRATION\b|\bAGRICOLE\b|\bUNION DES\b|\bDES PRODUCTEURS\b|\bSCOOPS?\b|- CA$"
    c = re.sub(pattern, "", c)
    cafe_pattern = r"(?:DU CAFE&CACAO|DU CAFE & CACAO|CAFE ET CACAO|CAFE CACAO)"
    c = re.sub(cafe_pattern, " CAFE ET CACAO ", c, flags=re.IGNORECASE)
    return " ".join(c.split())


def format_trase_id(geocode):
    if pd.isna(geocode):
        return None
    match = re.search(r"CI-(\d+)\.(\d+)\.(\d+)_", str(geocode))
    if match:
        return f"CI-{int(match.group(1)):02d}{int(match.group(2)):02d}{int(match.group(3)):02d}"
    return None


# =============================================================================
# MAIN EXECUTION BLOCK
# =============================================================================
def main():
    print("--- Phase 0: Setup ---")

    parser = argparse.ArgumentParser(
        description="Integrate user cooperative data with the Trase Earth base map."
    )
    parser.add_argument(
        "--default-year",
        type=int,
        required=True,
        help="Fallback year if the CSV is missing a YEAR column (e.g., 2024)",
    )
    args = parser.parse_args()
    fallback_year = args.default_year

    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"

    PATHS = {
        "base_geojson": DATA_DIR / "cote-d-ivoire-cocoa-cooperatives.geojson",
        "ci_departments": DATA_DIR / "ci_departments.geojson",
        "updated_geojson": DATA_DIR / "updated_trase_coops_with_user_data.geojson",
    }

    # Verify base mapping files exist
    for name, path in list(PATHS.items())[:2]:
        if not path.exists():
            print(
                f"❌ ERROR: Missing required base file '{path.name}'. Please ensure it is placed in the 'data' folder."
            )
            return

    # Dynamic check for the user's CSV
    default_csv_path = DATA_DIR / "user_disclosure_data.csv"

    if default_csv_path.exists():
        PATHS["user_disclosure_csv"] = default_csv_path
        print(f"✅ Found user data file: {default_csv_path.name}")
    else:
        print(
            f"⚠️ Notice: '{default_csv_path.name}' was not found in the 'data' folder."
        )
        while True:
            try:
                custom_name = input(
                    "👉 Please enter the exact name of your CSV file (e.g., my_data.csv): "
                ).strip()

                # Automatically append .csv if the user forgot it
                if not custom_name.lower().endswith(".csv"):
                    custom_name += ".csv"

                custom_path = DATA_DIR / custom_name

                if custom_path.exists():
                    PATHS["user_disclosure_csv"] = custom_path
                    print(f"✅ Found '{custom_name}'!")
                    break
                else:
                    print(
                        f"❌ ERROR: Could not find '{custom_name}' in the 'data' folder. Please try again."
                    )
            except KeyboardInterrupt:
                print("\n\nExiting script. Goodbye!")
                sys.exit(0)

    # -------------------------------------------------------------------------
    # PHASE 1: LOAD & STANDARDIZE USER DATA (BULLETPROOF VERSION)
    # -------------------------------------------------------------------------
    print("\n--- Phase 1: Loading & Standardizing User Data ---")

    try:
        df_user = pd.read_csv(PATHS["user_disclosure_csv"], low_memory=False)
    except UnicodeDecodeError:
        print(
            "⚠️ Notice: UTF-8 encoding failed. Falling back to Latin-1 (common for Excel exports)."
        )
        df_user = pd.read_csv(
            PATHS["user_disclosure_csv"], low_memory=False, encoding="latin1"
        )

    df_user.columns = df_user.columns.str.upper()

    # Friendly Pre-Flight Check for Missing Columns
    possible_names = [
        "SUPPLIER_FULLNAME",
        "DISCL_SUPPLIER_FULLNAME",
        "SUPPLIER_ABRVNAME",
        "DISCL_SUPPLIER_ABRVNAME",
    ]
    possible_buyers = ["COMPANY", "BUYER"]

    has_name = any(col in df_user.columns for col in possible_names)
    has_buyer = any(col in df_user.columns for col in possible_buyers)

    if not has_name or not has_buyer:
        print("\n❌ DATA ERROR: Your CSV is missing required columns.")
        print(
            "Please ensure your CSV has at least one Cooperative Name column (e.g., 'SUPPLIER_FULLNAME')"
        )
        print("AND a Buyer column (e.g., 'COMPANY' or 'BUYER').")
        print(f"Columns found in your file: {list(df_user.columns)}\n")
        return

    # Extract names and coordinates
    name_col = (
        "SUPPLIER_FULLNAME"
        if "SUPPLIER_FULLNAME" in df_user.columns
        else "DISCL_SUPPLIER_FULLNAME"
    )
    abrv_col = (
        "SUPPLIER_ABRVNAME"
        if "SUPPLIER_ABRVNAME" in df_user.columns
        else "DISCL_SUPPLIER_ABRVNAME"
    )

    raw_names = (
        df_user.get(name_col) if name_col in df_user.columns else df_user.get(abrv_col)
    )
    if raw_names is None:
        raw_names = df_user.get(abrv_col)
    df_user["CLEAN_NAME"] = raw_names.apply(clean_coop_name)

    # Bulletproof the Coordinates (Fix French commas and force floats)
    for col, default_name in [
        ("LONGITUDE", "DISCL_LONGITUDE"),
        ("LATITUDE", "DISCL_LATITUDE"),
    ]:
        target_col = col if col in df_user.columns else default_name
        if target_col in df_user.columns:
            df_user[col] = (
                df_user[target_col].astype(str).str.replace(",", ".").str.strip()
            )
            df_user[col] = pd.to_numeric(df_user[col], errors="coerce")
        else:
            df_user[col] = np.nan

    # Establish the Year
    year_col = "YEAR" if "YEAR" in df_user.columns else "DISCL_YEAR"
    if year_col in df_user.columns:
        df_user["USER_YEAR"] = (
            pd.to_numeric(df_user[year_col], errors="coerce")
            .fillna(fallback_year)
            .astype(int)
        )
    else:
        df_user["USER_YEAR"] = fallback_year

    buyer_col = "COMPANY" if "COMPANY" in df_user.columns else "BUYER"
    df_user["USER_BUYER_NAME"] = df_user[buyer_col].apply(remove_accents)

    df_user = df_user.dropna(subset=["CLEAN_NAME"])

    # -------------------------------------------------------------------------
    # PHASE 2: LOAD BASE GEOJSON & BUILD MATCHING DICTIONARY
    # -------------------------------------------------------------------------
    print("--- Phase 2: Loading Base GeoJSON & Matching ---")

    gdf_base = gpd.read_file(PATHS["base_geojson"])

    if "buyers_list" not in gdf_base.columns:
        gdf_base["buyers_list"] = [[] for _ in range(len(gdf_base))]

    gdf_base["CLEAN_BASE_NAME"] = (
        gdf_base["full_name"]
        .fillna(gdf_base["abbreviated_name"])
        .apply(clean_coop_name)
    )
    gdf_base["BASE_YEAR"] = (
        pd.to_numeric(gdf_base["year"], errors="coerce").fillna(0).astype(int)
    )
    gdf_base["ID_YEAR_KEY"] = (
        gdf_base["coop_stable_id"].astype(str) + "_" + gdf_base["BASE_YEAR"].astype(str)
    )

    exact_name_to_id = dict(
        zip(gdf_base["CLEAN_BASE_NAME"], gdf_base["coop_stable_id"])
    )
    base_names_list = gdf_base["CLEAN_BASE_NAME"].dropna().unique().tolist()

    fuzzy_match_map = {}
    for user_name in df_user["CLEAN_NAME"].unique():
        if pd.isna(user_name):
            continue
        if user_name in exact_name_to_id:
            fuzzy_match_map[user_name] = exact_name_to_id[user_name]
        else:
            match, score, _ = process.extractOne(
                user_name, base_names_list, scorer=fuzz.token_sort_ratio
            )
            if score >= 90 and match is not None:
                fuzzy_match_map[user_name] = exact_name_to_id[match]

    df_user["MATCHED_COOP_ID"] = df_user["CLEAN_NAME"].map(fuzzy_match_map)
    df_user["ID_YEAR_KEY"] = (
        df_user["MATCHED_COOP_ID"].astype(str).replace(r"\.0$", "", regex=True)
        + "_"
        + df_user["USER_YEAR"].astype(str)
    )

    # Segment the data
    base_keys = set(gdf_base["ID_YEAR_KEY"])

    mask_has_id = df_user["MATCHED_COOP_ID"].notna()
    mask_exact = mask_has_id & df_user["ID_YEAR_KEY"].isin(base_keys)
    mask_roll_forward = mask_has_id & ~df_user["ID_YEAR_KEY"].isin(base_keys)
    mask_new = df_user["MATCHED_COOP_ID"].isna()

    df_exact = df_user[mask_exact].copy()
    df_roll_forward = df_user[mask_roll_forward].copy()
    df_new = df_user[mask_new].copy()

    print(f"-> Found {len(df_exact)} EXACT matches (ID + Year).")
    print(
        f"-> Found {len(df_roll_forward)} ROLL-FORWARD matches (Existing ID, New Year)."
    )
    print(f"-> Identified {len(df_new)} BRAND NEW cooperatives.")

    # -------------------------------------------------------------------------
    # PHASE 3: UPDATE EXACT MATCHES
    # -------------------------------------------------------------------------
    if not df_exact.empty:
        print("--- Phase 3: Updating Exact Matches ---")
        user_buyers_exact = (
            df_exact.groupby("ID_YEAR_KEY")["USER_BUYER_NAME"]
            .apply(lambda x: list(set(x.dropna())))
            .to_dict()
        )

        def update_buyers(row):
            key = row["ID_YEAR_KEY"]
            if key in user_buyers_exact:
                existing = (
                    list(row["buyers_list"])
                    if isinstance(row["buyers_list"], list)
                    else []
                )
                combined = sorted(list(set(existing + user_buyers_exact[key])))
                row["buyers_list"] = combined
                row["buyers"] = ", ".join(combined)
            return row

        gdf_base = gdf_base.apply(update_buyers, axis=1)

    # -------------------------------------------------------------------------
    # PHASE 4: PROCESS ROLL-FORWARDS
    # -------------------------------------------------------------------------
    if not df_roll_forward.empty:
        print("--- Phase 4: Processing Roll-Forwards ---")
        roll_forward_features = []

        rf_grouped = df_roll_forward.groupby(["MATCHED_COOP_ID", "USER_YEAR"])

        for (coop_id, new_year), group in rf_grouped:
            base_records = gdf_base[gdf_base["coop_stable_id"] == coop_id]
            if base_records.empty:
                continue

            latest_record = base_records.loc[base_records["BASE_YEAR"].idxmax()].copy()

            latest_record["year"] = new_year
            latest_record["repeated_from_past_year"] = True

            user_buyers = list(set(group["USER_BUYER_NAME"].dropna()))
            latest_record["buyers_list"] = user_buyers
            latest_record["buyers"] = ", ".join(user_buyers)

            roll_forward_features.append(latest_record)

        if roll_forward_features:
            gdf_roll_forward = gpd.GeoDataFrame(roll_forward_features, crs="EPSG:4326")
            gdf_base = pd.concat([gdf_base, gdf_roll_forward], ignore_index=True)

    # -------------------------------------------------------------------------
    # PHASE 5: PROCESS BRAND NEW COOPERATIVES
    # -------------------------------------------------------------------------
    if not df_new.empty:
        print("--- Phase 5: Processing Brand New Cooperatives ---")
        df_new = df_new.dropna(subset=["LONGITUDE", "LATITUDE"])

        if not df_new.empty:
            gdf_new = gpd.GeoDataFrame(
                df_new,
                geometry=gpd.points_from_xy(df_new.LONGITUDE, df_new.LATITUDE),
                crs="EPSG:4326",
            )

            gdf_depts = gpd.read_file(PATHS["ci_departments"])
            if gdf_depts.crs is None or gdf_depts.crs.to_string() != "EPSG:4326":
                gdf_depts = gdf_depts.to_crs("EPSG:4326")

            gdf_new = gpd.sjoin(
                gdf_new,
                gdf_depts[["LVL_4_CODE", "LVL_4_NAME", "geometry"]],
                how="left",
                predicate="intersects",
            )
            gdf_new = gdf_new[~gdf_new.index.duplicated(keep="first")]

            max_existing_id = pd.to_numeric(
                gdf_base["coop_stable_id"], errors="coerce"
            ).max()
            max_id = int(max_existing_id) if pd.notna(max_existing_id) else 0

            new_names = gdf_new["CLEAN_NAME"].unique()
            new_id_map = {name: (max_id + i + 1) for i, name in enumerate(new_names)}
            gdf_new["NEW_STABLE_ID"] = gdf_new["CLEAN_NAME"].map(new_id_map)

            new_features = []
            for (new_id, new_year), group in gdf_new.groupby(
                ["NEW_STABLE_ID", "USER_YEAR"]
            ):
                row = group.iloc[0].copy()
                user_buyers = list(set(group["USER_BUYER_NAME"].dropna()))

                feat = {
                    "coop_stable_id": new_id,
                    "year": new_year,
                    "repeated_from_past_year": False,
                    "abbreviated_name": (
                        row.get(abrv_col, row["CLEAN_NAME"])
                        if pd.notna(row.get(abrv_col))
                        else row["CLEAN_NAME"]
                    ),
                    "full_name": (
                        row.get(name_col, row["CLEAN_NAME"])
                        if pd.notna(row.get(name_col))
                        else row["CLEAN_NAME"]
                    ),
                    "latitude": row["LATITUDE"],
                    "longitude": row["LONGITUDE"],
                    "department_name": row["LVL_4_NAME"],
                    "department_id": row["LVL_4_CODE"],
                    "department_trase_id": format_trase_id(row["LVL_4_CODE"]),
                    "buyers_list": user_buyers,
                    "buyers": ", ".join(user_buyers),
                    "geometry": row["geometry"],
                }
                new_features.append(feat)

            gdf_new_formatted = gpd.GeoDataFrame(new_features, crs="EPSG:4326")
            gdf_base = pd.concat([gdf_base, gdf_new_formatted], ignore_index=True)
        else:
            print(
                "--- Phase 5: Brand new cooperatives lacked coordinates and were skipped ---"
            )
    else:
        print("--- Phase 5: No Brand New Cooperatives to Process ---")

    # Cleanup temporary tracking columns before saving
    gdf_final = gdf_base.drop(
        columns=["CLEAN_BASE_NAME", "BASE_YEAR", "ID_YEAR_KEY", "buyers_list"],
        errors="ignore",
    )

    # -------------------------------------------------------------------------
    # PHASE 6: EXPORT UPDATED GEOJSON
    # -------------------------------------------------------------------------
    print("--- Phase 6: Exporting Final Dataset ---")
    gdf_final.to_file(PATHS["updated_geojson"], driver="GeoJSON")
    print(
        f"✅ Success! Your updated cooperative map is saved at: {PATHS['updated_geojson']}"
    )


if __name__ == "__main__":
    main()
