"""
supplier_map_tools.py: reusable steps for building a supplier map (which
cooperatives exist, where they are, and which companies buy from them) from
company disclosures.

The model needs two tables built from company disclosures (see
docs/INPUT_DATA.md): supplier LINKS (one row per supplier x buyer) and
SUPPLIERS (one row per supplier). How you get there depends on the
disclosures you find; the steps below are the parts of the Côte d'Ivoire
workflow (examples/cote_divoire_2024/) that apply anywhere:

  1. normalise_text / remove_ignore_phrases   make names comparable
  2. build_fuzzy_map                          match new names to a reference list
                                              (e.g. last year's suppliers)
  3. locate_suppliers                         assign each supplier to a region:
                                              fix tables -> region name ->
                                              reference list -> coordinates
  4. fill_from_reference                      fill gaps from a reference table
     impute_farmer_numbers                    farmers per link (docs/HOW_THE_MODEL_WORKS.md, Step 5)
  5. make_links                               decide the BUYER of each link,
                                              combine certifications, number links
  6. check_model_tables                       check the result against DATA_SPEC

Requires: pandas, numpy, geopandas, fuzzywuzzy.
"""
import re
import unicodedata

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# 1. Text
# --------------------------------------------------------------------------- #
def normalise_text(text):
    """Remove accents, upper-case, strip spaces. Empty/NaN -> None."""
    if pd.isna(text) or text == "" or str(text).lower() == 'nan':
        return None
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('utf-8')
    return text.upper().strip()


def remove_ignore_phrases(text, ignore_phrases):
    """Remove generic words (e.g. COOPERATIVE, SOCIETE, DE) before fuzzy matching."""
    if not isinstance(text, str):
        return text
    for phrase in ignore_phrases:
        text = re.sub(re.escape(phrase), '', text, flags=re.IGNORECASE)
    return ' '.join(text.split())


# Generic words ignored when matching Ivorian cooperative names (French).
# Adapt for other languages (e.g. English: "SOCIETY", "UNION", "FARMERS", "OF").
IGNORE_PHRASES_FR = [
    "SOCIETE", "COOPERATIVE", "COOPÉRATIVE", "AVEC", "CONSEIL D'ADMINISTRATION", "AGRICOLE",
    "DES", "PRODUCTEURS", "COOP", "WAREHOUSE", "SAND BOX", "-CA", "COOPÉRATIVE", "SOCIÉTÉ",
    "CONSEILD'ADMINISTRATION", "AGRICULTEURS", "ET", "DE",
]


# --------------------------------------------------------------------------- #
# 2. Fuzzy matching to a reference list
# --------------------------------------------------------------------------- #
def build_fuzzy_map(new_names, reference_names, ignore_phrases=IGNORE_PHRASES_FR,
                    threshold=90, verbose=True):
    """
    Map each new name to the most similar reference name, if similar enough.

    Similarity: fuzzywuzzy token_sort_ratio on names with generic words
    removed (0-100). Returns {new_name: reference_name} for scores >= threshold.
    Print-outs let you review every match; check them by hand.
    """
    from fuzzywuzzy import fuzz, process
    reference_names = list(pd.Series(reference_names).dropna().unique())
    new_names = list(pd.Series(new_names).dropna().unique())
    ref_clean = [remove_ignore_phrases(x, ignore_phrases) for x in reference_names]
    new_clean = [remove_ignore_phrases(x, ignore_phrases) for x in new_names]

    mapping = {}
    for val in new_clean:
        match, score = process.extractOne(val, ref_clean, scorer=fuzz.token_sort_ratio)
        if score >= threshold and match is not None:
            matched_original = reference_names[ref_clean.index(match)]
            if verbose:
                print(f"Matching {val} to {matched_original} with score {score}")
            mapping[val] = matched_original
    return mapping


# --------------------------------------------------------------------------- #
# 3. Locating suppliers in regions
# --------------------------------------------------------------------------- #
def locate_suppliers(df, regions, *, area_col, acronym_col, lat_col, lon_col,
                     region_code_col, region_name_col,
                     fix_area_names=None, area_from_acronym=None,
                     reference=None, reference_acronym_col=None, reference_code_col=None,
                     reference_name_col=None):
    """
    Assign a region code to every supplier, trying in order:

      a. fix_area_names      {written area name: correct region name, '' or None}
                             typos, villages -> region, '' for "too broad",
                             None for foreign/garbage
      b. area_from_acronym   {supplier acronym: region name}, for suppliers
                             whose disclosure gives no usable place name
      c. the region-name list of `regions`
      d. `reference`         last year's suppliers (same acronym -> same region)
      e. coordinates         point-in-polygon with `regions` (EPSG:4326)

    Adds REGION_CODE and REGION_NAME_CLEAN; drops rows where neither could be
    found. Returns the new data frame.
    """
    import geopandas as gpd
    df = df.copy()
    regions = regions.copy()
    regions['NAME_CLEAN'] = regions[region_name_col].apply(normalise_text)
    name_to_code = dict(zip(regions['NAME_CLEAN'], regions[region_code_col]))
    code_to_name = dict(zip(regions[region_code_col], regions['NAME_CLEAN']))

    df[area_col] = df[area_col].apply(normalise_text)

    # a. manual fixes
    if fix_area_names:
        df[area_col] = df[area_col].replace(fix_area_names)
    # b. place from acronym when the area is missing or too broad
    if area_from_acronym:
        missing = (df[area_col] == '') | (df[area_col].isna())
        df.loc[missing, area_col] = df.loc[missing, acronym_col].map(area_from_acronym)

    # c. region name -> code
    df['REGION_NAME_CLEAN'] = df[area_col].apply(normalise_text)
    df['REGION_CODE'] = df['REGION_NAME_CLEAN'].map(name_to_code)

    # d. last year's location of the same supplier
    if reference is not None:
        ref = reference.dropna(subset=[reference_acronym_col]).drop_duplicates(reference_acronym_col)
        acr_to_code = dict(zip(ref[reference_acronym_col], ref[reference_code_col]))
        acr_to_name = dict(zip(ref[reference_acronym_col], ref[reference_name_col].apply(normalise_text)))
        no_code = df['REGION_CODE'].isna()
        df.loc[no_code, 'REGION_CODE'] = df.loc[no_code, acronym_col].map(acr_to_code)
        df.loc[no_code, 'REGION_NAME_CLEAN'] = df.loc[no_code, acronym_col].map(acr_to_name)

    # e. coordinates
    needs = df['REGION_CODE'].isna() & df[lat_col].notna() & df[lon_col].notna()
    if needs.sum() > 0:
        pts = gpd.GeoDataFrame(df.loc[needs],
                               geometry=gpd.points_from_xy(df.loc[needs, lon_col], df.loc[needs, lat_col]),
                               crs="EPSG:4326")
        if regions.crs != "EPSG:4326":
            regions = regions.to_crs("EPSG:4326")
        joined = gpd.sjoin(pts, regions[[region_code_col, 'NAME_CLEAN', 'geometry']], how='left', predicate='within')
        joined = joined[~joined.index.duplicated(keep='first')]
        df.loc[joined.index, 'REGION_CODE'] = df.loc[joined.index, 'REGION_CODE'].fillna(joined[region_code_col])
        df.loc[joined.index, 'REGION_NAME_CLEAN'] = df.loc[joined.index, 'REGION_NAME_CLEAN'].fillna(joined['NAME_CLEAN'])

    # sync name and code
    df['REGION_NAME_CLEAN'] = df['REGION_NAME_CLEAN'].fillna(df['REGION_CODE'].map(code_to_name))
    df['REGION_CODE'] = df['REGION_CODE'].fillna(df['REGION_NAME_CLEAN'].map(name_to_code))

    n0 = len(df)
    df = df.dropna(subset=['REGION_NAME_CLEAN', 'REGION_CODE'], how='all')
    print(f"Located {df['REGION_CODE'].notna().sum()} of {n0} rows; dropped {n0 - len(df)}; "
          f"still missing a code: {df['REGION_CODE'].isna().sum()}")
    return df


# --------------------------------------------------------------------------- #
# 4. Filling gaps from a reference table
# --------------------------------------------------------------------------- #
def fill_from_reference(new_df, old_df, join_key, verbose=True):
    """Fill missing values in new_df with old_df's values for the same key
    (only columns present in both; first old row per key)."""
    new_df = new_df.copy()
    old_df = old_df.copy()
    new_df[join_key] = new_df[join_key].astype(str).str.strip()
    old_df[join_key] = old_df[join_key].astype(str).str.strip()
    common_cols = [c for c in new_df.columns if c in old_df.columns and c != join_key]
    old_clean = old_df.dropna(subset=[join_key]).drop_duplicates(subset=[join_key])
    for col in common_cols:
        before = new_df[col].isna().sum()
        new_df[col] = new_df[col].fillna(new_df[join_key].map(old_clean.set_index(join_key)[col]))
        if verbose and before - new_df[col].isna().sum() > 0:
            print(f"  -> Filled {before - new_df[col].isna().sum()} missing values in '{col}'")
    return new_df


# --------------------------------------------------------------------------- #
# 4b. Farmer numbers per link
# --------------------------------------------------------------------------- #
def _round_mean(series):
    """Mean ignoring missing values, rounded to whole farmers (NaN if all missing).
    numpy rounds halves to even, like R's round()."""
    m = series.mean(skipna=True)
    return np.round(m, 0) if pd.notna(m) else np.nan


def impute_farmer_numbers(df, *, coop_col, year_col, company_col, trader_col, disclosed_col,
                          sources_that_are_not_buyers=("RAINFOREST ALLIANCE",),
                          history=None):
    """
    Number of farmers for every cooperative-buyer link (docs/HOW_THE_MODEL_WORKS.md, Step 5):

      1. the buyer's own figure: mean of what the same company (and trader)
         disclosed for this cooperative in the year; if none that year, the
         mean of its figures for this cooperative in other years
      2. otherwise, the mean of the figures of the OTHER buyers of the same
         cooperative: the same year first, then other years
         (Rainforest Alliance figures are kept separate: they count certified
         farmers, not supply)
      3. otherwise left empty -> NUM_FARMERS is NaN, and the model draws a
         size from all disclosed sizes (on average, the overall mean)

    Parameters
    ----------
    df : one row per disclosure (cooperative x disclosing company), current year
    coop_col : column identifying the cooperative (same key in df and history)
    history : optional, earlier years' disclosures with the same columns. Used
        only to fill gaps ("other years"); never overwrites a current figure.

    Returns df with three new columns:
      NB_FARMERS_COMPANY_YEAR   after step 1
      NUM_FARMERS               after step 2 (what the model uses)
      NUM_FARMERS_EXTRAPOLATED  step 3 done here too: the year's mean link size
                                (for publication only; the model does this
                                itself, by drawing)
    """
    cols = [coop_col, year_col, company_col, trader_col, disclosed_col]
    cur = df.copy()
    cur['_ROW'] = np.arange(len(cur))
    stack = cur[cols + ['_ROW']]
    if history is not None and len(history) > 0:
        hist = history[cols].copy()
        hist['_ROW'] = -1
        stack = pd.concat([stack, hist], ignore_index=True)
    stack = stack.copy()
    stack['_NOT_SOURCE_ONLY'] = (~stack[company_col].isin(sources_that_are_not_buyers)).astype(object)
    stack.loc[stack[company_col].isna(), '_NOT_SOURCE_ONLY'] = None   # as in R: unknown company = own group
    disclosed = pd.to_numeric(stack[disclosed_col], errors='coerce')

    def grouped(values, keys):
        return values.groupby([stack[k] for k in keys], dropna=False).transform(_round_mean)

    # 1. the same company's figures for this cooperative: same year, then other years
    nb = grouped(disclosed, [coop_col, year_col, company_col, trader_col])
    nb = nb.fillna(grouped(nb, [coop_col, company_col, trader_col]))
    # 2. other buyers of the same cooperative: same year, then other years
    num = nb.fillna(grouped(nb, [coop_col, year_col, '_NOT_SOURCE_ONLY']))
    num = num.fillna(grouped(num, [coop_col, '_NOT_SOURCE_ONLY']))
    # (3.) the year's average link size, for publication only
    extrap = num.fillna(grouped(num, [year_col, '_NOT_SOURCE_ONLY']))

    keep = (stack['_ROW'] >= 0).values
    order = stack['_ROW'].values[keep]
    for name, values in (('NB_FARMERS_COMPANY_YEAR', nb), ('NUM_FARMERS', num),
                         ('NUM_FARMERS_EXTRAPOLATED', extrap)):
        out = np.full(len(cur), np.nan)
        out[order] = values.values[keep]
        cur[name] = out
    return cur.drop(columns='_ROW')


# --------------------------------------------------------------------------- #
# 5. Links table
# --------------------------------------------------------------------------- #
def aggregate_certs(series):
    """Combine certification names into one sorted ' + '-separated string."""
    items = []
    for x in series:
        if isinstance(x, list):
            items.extend(x)
        elif pd.notna(x):
            items.append(x)
    return " + ".join(sorted(set(items)))


def make_links(df, year, *, supplier_col='SUPPLIER_NUMBER', trader_col='TRADER',
               source_col='DISCLOSED_BY', cert_col='CERTIFICATION',
               sources_that_are_not_buyers=("RAINFOREST ALLIANCE",)):
    """
    One row per supplier x buyer, from one row per disclosure.

    df has one row per disclosure: the supplier (supplier_col), the trader
    named in the disclosure if any (trader_col), the company that published
    it (source_col) and a certification (cert_col).

    BUYER = the trader named in the disclosure if there is one, otherwise the
    company that disclosed (e.g. a chocolate maker), except for sources that
    never buy (certification schemes). BUYER_IS_TRADER says which.
    Certifications are combined per link; LINK_ID numbers the links
    ("<year>-<n>").
    """
    df = df.copy()
    df['BUYER'] = np.where(df[trader_col].isna() & ~df[source_col].isin(sources_that_are_not_buyers),
                           df[source_col], df[trader_col])
    df['BUYER_IS_TRADER'] = df[trader_col].notna()
    df['CERTIFICATIONS'] = df.groupby([supplier_col, 'YEAR', 'BUYER'], dropna=False)[cert_col].transform(aggregate_certs)
    df = df.drop_duplicates(subset=[supplier_col, 'YEAR', 'BUYER'], keep='first')
    df['LINK_ID'] = str(year) + "-" + (df.groupby('YEAR').cumcount() + 1).astype(str)
    return df


# --------------------------------------------------------------------------- #
# 6. Checks
# --------------------------------------------------------------------------- #
LINK_COLUMNS = ["SUPPLIER_NUMBER", "YEAR", "REGION_CODE", "SUPPLIER_SHORT_NAME", "SUPPLIER_NAME",
                "BUYER", "BUYER_IS_TRADER", "NUMBER_OF_FARMERS", "CERTIFICATIONS", "CERTIFIED",
                "LINK_ID", "DISCLOSED_BY"]
SUPPLIER_COLUMNS = ["SUPPLIER_NUMBER", "YEAR", "REGION_CODE", "SUPPLIER_SHORT_NAME", "SUPPLIER_NAME",
                    "CERTIFICATIONS", "CERTIFIED"]


def check_model_tables(links, suppliers, region_codes):
    """Check the two supplier tables against docs/INPUT_DATA.md. Returns a list of problems."""
    problems = []
    for name, df, cols in (("supplier_links", links, LINK_COLUMNS), ("suppliers", suppliers, SUPPLIER_COLUMNS)):
        missing = [c for c in cols if c not in df.columns]
        if missing:
            problems.append(f"{name}: missing columns {missing}")
    if not problems:
        if suppliers['SUPPLIER_NUMBER'].duplicated().any():
            problems.append("suppliers: SUPPLIER_NUMBER is not unique")
        bad = set(links['REGION_CODE'].dropna()) - set(region_codes)
        if bad:
            problems.append(f"supplier_links: {len(bad)} region codes not in the region list, e.g. {sorted(bad)[:5]}")
        if not set(links['SUPPLIER_NUMBER']).issubset(set(suppliers['SUPPLIER_NUMBER'])):
            problems.append("supplier_links: some SUPPLIER_NUMBER are not in suppliers")
        trader_flag = links['BUYER_IS_TRADER'].astype(str).str.upper()
        if not trader_flag.isin(["TRUE", "FALSE"]).all():
            problems.append("supplier_links: BUYER_IS_TRADER must be TRUE or FALSE")
        if ((trader_flag == "TRUE") & links['BUYER'].isna()).any():
            problems.append("supplier_links: BUYER_IS_TRADER is TRUE but BUYER is empty")
        if links['LINK_ID'].duplicated().any():
            problems.append("supplier_links: LINK_ID is not unique")
        if (pd.to_numeric(links['NUMBER_OF_FARMERS'], errors='coerce') < 0).any():
            problems.append("supplier_links: negative NUMBER_OF_FARMERS")
    for p in problems:
        print("PROBLEM:", p)
    if not problems:
        print("Supplier tables look fine.")
    return problems
