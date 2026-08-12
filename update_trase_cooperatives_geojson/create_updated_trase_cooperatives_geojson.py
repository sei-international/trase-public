"""
DESCRIPTION:
This script allows users to take their own messy cooperative disclosure data (CSV), 
clean it, and merge it with the official base GeoJSON dataset downloaded from trase.earth.
It matches cooperatives using text normalization and fuzzy matching on BOTH Name and Year.
It updates existing cooperatives, rolls forward existing cooperatives for new years, 
and creates brand new spatial features for unknown cooperatives using department polygons.

HOW TO RUN:
   Open your terminal/command prompt and run the script:
       python update_trase_coops.py --fallback-year 2026
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
        return ""
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ASCII", "ignore")
        .decode("ASCII")
        .upper()
        .strip()
    )


def clean_coop_name(col_name):
    """
    Cleans cooperative names by stripping accents and generic administrative boilerplate.
    Falls back to the normalized original name if stripping leaves an empty string.
    """
    if not isinstance(col_name, str) or pd.isna(col_name):
        return np.nan

    # Store normalized original for fallback
    original_normalized = " ".join(remove_accents(col_name).split())
    if not original_normalized:
        return np.nan

    c = original_normalized
    c = re.sub(r"\.|[(]|[)]| WAREHOUSE$", "", c)
    c = re.sub(r"\n|_|/|-", " ", c)
    pattern = r"\bCOOP CA\b|\bSAND BOX\b|\bCOOP\b|\bWAREHOUSE\b|\bAVEC CONSEIL D'ADMINISTRATION\b|\bAGRICOLE\b|\bUNION DES\b|\bDES PRODUCTEURS\b|\bSCOOPS?\b|- CA$"
    c = re.sub(pattern, "", c)
    cafe_pattern = r"(?:DU CAFE&CACAO|DU CAFE & CACAO|CAFE ET CACAO|CAFE CACAO)"
    c = re.sub(cafe_pattern, " CAFE ET CACAO ", c, flags=re.IGNORECASE)

    cleaned = " ".join(c.split())

    # Defense check: If cleaning stripped everything, fall back to normalized original
    return cleaned if cleaned else original_normalized


def format_trase_id(geocode):
    if pd.isna(geocode):
        return None
    match = re.search(r"CI-(\d+)\.(\d+)\.(\d+)_", str(geocode))
    if match:
        return f"CI-{int(match.group(1)):02d}{int(match.group(2)):02d}{int(match.group(3)):02d}"
    return None


def parse_locale_float(val):
    """Parses numeric values across US, EU, and French formatting variations."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return float(val)

    # Strip regular spaces, non-breaking spaces (\xa0), and surrounding whitespace
    val_str = str(val).strip().replace(" ", "").replace("\xa0", "")
    if not val_str or val_str.lower() in ("nan", "none", "null"):
        return np.nan

    # Both punctuation marks present: infer separator roles by order
    if "." in val_str and "," in val_str:
        if val_str.find(",") < val_str.find("."):
            val_str = val_str.replace(",", "")  # US style: 1,234.56 -> 1234.56
        else:
            val_str = val_str.replace(".", "").replace(",", ".")  # EU style: 1.234,56 -> 1234.56
    elif "," in val_str:
        val_str = val_str.replace(",", ".")  # French decimal comma: 48,8584 -> 48.8584

    try:
        return float(val_str)
    except ValueError:
        return np.nan


# =============================================================================
# MAIN EXECUTION BLOCK
# =============================================================================
def main():
    print("--- Phase 0: Setup ---")

    parser = argparse.ArgumentParser(
        description="Integrate user cooperative data with the Trase Earth base map."
    )
    parser.add_argument(
        "--fallback-year",
        type=int,
        required=True,
        help="Fallback year if the CSV is missing a YEAR column (e.g., 2024)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite the output GeoJSON file without asking for confirmation",
    )
    args = parser.parse_args()
    fallback_year = args.fallback_year

    BASE_DIR = Path(__file__).resolve().parent
    DATA_DIR = BASE_DIR / "data"

    PATHS = {
        "base_geojson": DATA_DIR / "cote-d-ivoire-cocoa-cooperatives.geojson",
        "ci_departments": DATA_DIR / "ci_departments.geojson",
        "user_disclosure_csv": DATA_DIR / "user_disclosure.csv",
        "updated_geojson": DATA_DIR / "updated_trase_coops_with_user_data.geojson",
    }
    
    # Exit if requried files aren't present
    if not PATHS["user_disclosure_csv"].exists():
        print(f"⚠️ Could not find the default file: {PATHS['user_disclosure_csv'].name}")
        custom_name = input("Please type the exact name of your CSV file located in the 'data' folder: ").strip()
        PATHS["user_disclosure_csv"] = DATA_DIR / custom_name

    # Verify base mapping files exist
    required_paths = [PATHS["base_geojson"], PATHS["ci_departments"], PATHS["user_disclosure_csv"]]
    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        print("❌ Missing required file(s):", ", ".join(path.name for path in missing_paths))
        sys.exit(1)

    # -------------------------------------------------------------------------
    # PHASE 1: LOAD & STANDARDIZE USER DATA (CONSOLIDATED)
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

    # 1. Resolve Column Aliases
    possible_names = [
        "SUPPLIER_FULLNAME",
        "DISCL_SUPPLIER_FULLNAME",
        "SUPPLIER_ABRVNAME",
        "DISCL_SUPPLIER_ABRVNAME",
    ]
    possible_abrvs = ["SUPPLIER_ABRVNAME", "DISCL_SUPPLIER_ABRVNAME"]
    possible_buyers = ["COMPANY", "BUYER"]
    possible_lons = ["LONGITUDE", "DISCL_LONGITUDE"]
    possible_lats = ["LATITUDE", "DISCL_LATITUDE"]
    possible_years = ["YEAR", "DISCL_YEAR"]

    name_col = next((col for col in possible_names if col in df_user.columns), None)
    abrv_col = next((col for col in possible_abrvs if col in df_user.columns), None)
    buyer_col = next((col for col in possible_buyers if col in df_user.columns), None)
    lon_col = next((col for col in possible_lons if col in df_user.columns), None)
    lat_col = next((col for col in possible_lats if col in df_user.columns), None)
    year_col = next((col for col in possible_years if col in df_user.columns), None)

    # 2. Pre-Flight Check for Mandatory Metadata
    if not name_col or not buyer_col:
        print("\n❌ DATA ERROR: Your CSV is missing required columns.")
        print("Please ensure your CSV contains at least one Cooperative Name column")
        print("(e.g., 'SUPPLIER_FULLNAME') AND a Buyer column (e.g., 'COMPANY' or 'BUYER').")
        print(f"Columns found in your file: {list(df_user.columns)}\n")
        sys.exit(1)

    # 3. Standardize Standardized Derived Fields
    # Name cleaning
    raw_names = df_user[name_col] if name_col else df_user[abrv_col]
    df_user["CLEAN_NAME"] = raw_names.apply(clean_coop_name).replace(r"^\s*$", np.nan, regex=True)
    df_user = df_user.dropna(subset=["CLEAN_NAME"]).copy()

    # Original Name/Abrv fallback preserving fields
    df_user["RAW_FULL_NAME"] = df_user[name_col] if name_col in df_user.columns else df_user["CLEAN_NAME"]
    df_user["RAW_ABRV_NAME"] = df_user[abrv_col] if abrv_col and abrv_col in df_user.columns else df_user["CLEAN_NAME"]

    # Buyer Name
    df_user["USER_BUYER_NAME"] = df_user[buyer_col].fillna("UNKNOWN").apply(remove_accents)

    # Coordinates
    df_user["LONGITUDE"] = df_user[lon_col].apply(parse_locale_float) if lon_col else np.nan
    df_user["LATITUDE"] = df_user[lat_col].apply(parse_locale_float) if lat_col else np.nan

    df_user["LONGITUDE"] = df_user["LONGITUDE"].where(df_user["LONGITUDE"].between(-180, 180))
    df_user["LATITUDE"] = df_user["LATITUDE"].where(df_user["LATITUDE"].between(-90, 90))

    # Year
    if year_col:
        df_user["USER_YEAR"] = (
            pd.to_numeric(df_user[year_col], errors="coerce")
            .fillna(fallback_year)
            .astype(int)
        )
    else:
        df_user["USER_YEAR"] = fallback_year

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
    
    # Use Int64 (nullable integer) to avoid float '.0' artifacts entirely
    gdf_base["coop_stable_id"] = pd.to_numeric(gdf_base["coop_stable_id"], errors="coerce").astype("Int64")
    
    gdf_base["ID_YEAR_KEY"] = (
        gdf_base["coop_stable_id"].astype(str) + "_" + gdf_base["BASE_YEAR"].astype(str)
    )

    # -------------------------------------------------------------------------
    # FIX 1: DUPLICATE NAME HANDLING
    # -------------------------------------------------------------------------
    # Sort by BASE_YEAR descending before dropping duplicates. 
    # This ensures that if a name maps to multiple IDs, it defaults to the most recently active ID.
    name_id_pairs = gdf_base[["CLEAN_BASE_NAME", "coop_stable_id", "BASE_YEAR"]].dropna(subset=["CLEAN_BASE_NAME", "coop_stable_id"])
    name_id_pairs = name_id_pairs.sort_values("BASE_YEAR", ascending=False)

    conflicts = name_id_pairs[name_id_pairs.duplicated(subset=["CLEAN_BASE_NAME"], keep=False)]
    if not conflicts.empty:
        print("⚠️ Warning: Duplicate CLEAN_BASE_NAMEs in base GeoJSON map to different IDs:")
        for name, group in conflicts.groupby("CLEAN_BASE_NAME", dropna=False):
            ids = list(group["coop_stable_id"].unique())
            print(f"   - '{name}' maps to IDs: {ids}")
        print("   Defaulting mapping to the most recently active ID.")
        
    name_id_pairs = name_id_pairs.drop_duplicates(subset=["CLEAN_BASE_NAME"], keep="first")

    exact_name_to_id = dict(zip(name_id_pairs["CLEAN_BASE_NAME"], name_id_pairs["coop_stable_id"]))
    base_names_list = list(exact_name_to_id.keys())

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

    # Map directly to Int64 type
    df_user["MATCHED_COOP_ID"] = df_user["CLEAN_NAME"].map(fuzzy_match_map).astype("Int64")
    
    # Safe key generation 
    matched_id_str = df_user["MATCHED_COOP_ID"].astype(str).replace("<NA>", "UNMATCHED")
    df_user["ID_YEAR_KEY"] = matched_id_str + "_" + df_user["USER_YEAR"].astype(str)

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
            df_exact.groupby("ID_YEAR_KEY", dropna=False)["USER_BUYER_NAME"]
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

        rf_grouped = df_roll_forward.groupby(["MATCHED_COOP_ID", "USER_YEAR"], dropna=False)

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

        if df_new.empty:
            print("--- Phase 5: Brand new cooperatives lacked coordinates and were skipped ---")
        else:
            gdf_new = gpd.GeoDataFrame(
                df_new,
                geometry=gpd.points_from_xy(df_new.LONGITUDE, df_new.LATITUDE),
                crs="EPSG:4326",
            ).reset_index(drop=True)

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
                ["NEW_STABLE_ID", "USER_YEAR"], dropna=False
            ):
                row = group.iloc[0].copy()
                user_buyers = list(set(group["USER_BUYER_NAME"].dropna()))

                feat = {
                    "coop_stable_id": new_id,
                    "year": new_year,
                    "repeated_from_past_year": False,
                    "abbreviated_name": (
                        row["RAW_ABRV_NAME"]
                        if pd.notna(row.get("RAW_ABRV_NAME"))
                        else row["CLEAN_NAME"]
                    ),
                    "full_name": (
                        row["RAW_FULL_NAME"]
                        if pd.notna(row.get("RAW_FULL_NAME"))
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
    output_path = PATHS["updated_geojson"]

    if output_path.exists() and not args.force:
        confirm = (
            input(
                f"⚠️ Output file '{output_path.name}' already exists. Overwrite? [y/N]: "
            )
            .strip()
            .lower()
        )
        if confirm not in ("y", "yes"):
            print("❌ Operation cancelled. Existing file was not modified.")
            sys.exit(0)

    gdf_final.to_file(output_path, driver="GeoJSON")
    print(f"✅ Success! Your updated cooperative map is saved at: {output_path}")


if __name__ == "__main__":
    main()