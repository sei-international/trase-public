"""
Reformat the CSVs exported by cocoa_deforestation_metrics.js into three tables:

  cocoa_deforestation_by_region.csv
      cocoa deforestation and degradation (annual, allocation period) and
      cocoa emissions (from deforestation)
  territorial_emissions_by_region.csv
      territorial deforestation emissions
  territorial_deforestation_by_region.csv
      territorial deforestation, degradation, remaining undisturbed forest

and, if you pass the optional section B and C exports,
  cocoa_area_by_region.csv         REGION_ID, COCOA_HA
  cocoa_production_by_region.csv   REGION_ID, YEAR, COCOA_TONNES

These are the files the deforestation step of the model reads
(read_spatial_inputs() in countries/<country>/read_inputs.R).

Each table has one row per region ID and year (long format), and adds sums for
the higher administrative levels and the whole country ("multilevel").

Country settings are in COUNTRIES below (Côte d'Ivoire and Ghana included).
tests/test_earth_engine_exports.py checks the script on made-up Earth Engine exports.

Usage:
    python3 reshape_earth_engine_exports.py --country ci --input-dir <folder with Earth Engine CSVs> --output-dir <folder>
        [--cocoa-area-file <cocoa_area_...csv>] [--cocoa-production-file <cocoa_production_...csv>]

To add a country, add an entry to COUNTRIES (region ID column, a function
turning it into a region ID, and the ID prefix lengths of higher levels).
"""
import argparse
import os
import re
from functools import reduce

import pandas as pd


# --------------------------------------------------------------------------- #
# Region IDs
# --------------------------------------------------------------------------- #
def ci_code_to_region_id(code: str) -> str:
    """Convert a Côte d'Ivoire department code (e.g. 'CI-1.1.1_1') to a region ID (e.g., 'CI-010101')."""
    prefix, rest = code.split('-')
    nums = rest.split('_')[0].split('.')
    return prefix + '-' + ''.join([n.zfill(2) for n in nums])


def gadm_code_to_region_id(gid2: str) -> str:
    """Convert a GADM GID_2 code (e.g. 'GHA.1.2_1') to a region ID (e.g. 'GH-01.02')."""
    main, lvl = gid2.split('_')
    country = main[:3]
    nums = main[3:].lstrip('.').split('.')
    if len(nums) == 2:
        return f"{country[:2]}-{int(nums[0]):02d}.{int(nums[1]):02d}"
    elif len(nums) == 1:
        return f"{country[:2]}-{int(nums[0]):02d}"
    return gid2


# --------------------------------------------------------------------------- #
# Country settings
# --------------------------------------------------------------------------- #
COUNTRIES = {
    "ci": dict(
        national_id="CI",
        region_column="LVL_4_CODE",              # property of the Earth Engine region features
        to_region_id=ci_code_to_region_id,
        drop_columns=['system:index', 'LVL_1_CODE', 'LVL_1_NAME', 'LVL_2_CODE', 'LVL_2_NAME',
                      'LVL_3_CODE', 'LVL_3_NAME', 'LVL_4_CODE', 'LVL_4_NAME', '.geo'],
        # higher levels = first n characters of the region ID
        # (CI-010101 -> department CI-0101, region CI-01)
        aggregate_prefix_lengths=[7, 5],
    ),
    "gh": dict(
        national_id="GH",
        region_column="GID_2",
        to_region_id=gadm_code_to_region_id,
        drop_columns=['system:index', 'CC_2', 'COUNTRY', 'ENGTYPE_2', 'GID_0', 'GID_1', 'GID_2',
                      'HASC_2', 'NAME_1', 'NAME_2', 'NL_NAME_1', 'NL_NAME_2', 'TYPE_2', 'VARNAME_2', '.geo'],
        aggregate_prefix_lengths=[5],
    ),
}

# Earth Engine file names (without the _<code>.csv suffix), as written by the Earth Engine script
EARTH_ENGINE_FILES = ['eth2021_cocoa_tmfloss_annual_ha', 'eth2021_cocoa_tmfloss_total_15yr',
             'ghg_cd_gross_1yr', 'ghg_cd_gross_15yr', 'ghg_cd_net_1yr', 'ghg_cd_net_15yr',
             'ghg_territorial_gross_1yr', 'territorial_tmfloss_annual_ha', 'undisturbed_tmf_yearly']

# Earth Engine band-name prefix -> metric name. The first prefix contained in the
# band name wins; bands matching none (e.g. cd_1yr_tmf_def_*, the input for
# emissions) are dropped.
METRIC_MAP = {
    # 'loss' = undisturbed forest lost to deforestation OR degradation, now cocoa.
    # Trase's published data call these COCOA_DEFORESTATION_*; the names here
    # say what they measure.
    'cd_1yr_tmf_loss': 'COCOA_DEFORESTATION_AND_DEGRADATION_ANNUAL',
    'cd_15yr_tmf_loss': 'COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL',
    'ghg_cd_1yr_gross': 'COCOA_GROSS_EMISSIONS_ANNUAL',
    'ghg_cd_15yr_gross': 'COCOA_GROSS_EMISSIONS_15_YEARS_TOTAL',
    'ghg_cd_1yr_net': 'COCOA_NET_EMISSIONS_ANNUAL',
    'ghg_cd_15yr_net': 'COCOA_NET_EMISSIONS_15_YEARS_TOTAL',
    'ghg_uTMF_def_1yr_gross': 'CO2_GROSS_EMISSIONS_TERRITORIAL_DEFORESTATION',
    'uTMF_1yr_defo_by': 'TERRITORIAL_DEFORESTATION',
    'uTMF_1yr_degr_by': 'TERRITORIAL_DEGRADATION',
    'uTMF_remaining': 'TERRITORIAL_UNDISTURBED_FOREST',
}

COCOA_METRICS = ['COCOA_DEFORESTATION_AND_DEGRADATION_15_YEARS_TOTAL', 'COCOA_DEFORESTATION_AND_DEGRADATION_ANNUAL',
                 'COCOA_GROSS_EMISSIONS_15_YEARS_TOTAL', 'COCOA_GROSS_EMISSIONS_ANNUAL',
                 'COCOA_NET_EMISSIONS_15_YEARS_TOTAL', 'COCOA_NET_EMISSIONS_ANNUAL']
TERRITORIAL_DEF = ['TERRITORIAL_DEFORESTATION', 'TERRITORIAL_DEGRADATION', 'TERRITORIAL_UNDISTURBED_FOREST']
TERRITORIAL_EMISSIONS = ['CO2_GROSS_EMISSIONS_TERRITORIAL_DEFORESTATION']


# --------------------------------------------------------------------------- #
# Steps
# --------------------------------------------------------------------------- #
def read_gee_files(input_dir, code, settings):
    """Read the Earth Engine CSVs, add REGION_ID, drop region attributes, merge on REGION_ID."""
    dfs = []
    for name in EARTH_ENGINE_FILES:
        df = pd.read_csv(os.path.join(input_dir, f"{name}_{code}.csv"))
        df['REGION_ID'] = df[settings['region_column']].apply(settings['to_region_id'])
        df.drop(columns=settings['drop_columns'], inplace=True, errors='ignore')
        dfs.append(df)
    return reduce(lambda left, right: pd.merge(left, right, on='REGION_ID', how='outer'), dfs)


def get_metric_name(col):
    for k, v in METRIC_MAP.items():
        if k in col:
            return v
    return None


def to_long_by_year(merged):
    """One row per REGION_ID x YEAR, one column per metric."""
    year_cols = [col for col in merged.columns if re.search(r'(19\d{2}|20\d{2})', col)]
    long_df = merged.melt(id_vars=['REGION_ID'], value_vars=year_cols,
                          var_name='metric_year', value_name='value')
    long_df['YEAR'] = long_df['metric_year'].str.extract(r'(19\d{2}|20\d{2})').astype(int)
    long_df['METRIC'] = long_df['metric_year'].apply(get_metric_name)
    return long_df.pivot_table(index=['REGION_ID', 'YEAR'], columns='METRIC', values='value').reset_index()


def aggregate_spatial_levels(df, national_id, prefix_lengths):
    """Add sums for higher administrative levels (ID prefixes) and the whole country."""
    df = df.copy()
    level_cols = [f'LEVEL_{n}_ID' for n in prefix_lengths]
    for n, col in zip(prefix_lengths, level_cols):
        df[col] = df['REGION_ID'].apply(lambda region_id, n=n: region_id[:n])
    df['NATIONAL_ID'] = national_id
    metric_cols = [c for c in df.columns if c not in ['REGION_ID', 'YEAR', 'NATIONAL_ID'] + level_cols]

    parts = [df.drop(columns=level_cols + ['NATIONAL_ID'])]
    for col in level_cols + ['NATIONAL_ID']:
        agg = df.groupby([col, 'YEAR'])[metric_cols].sum().reset_index()
        agg['REGION_ID'] = agg[col]
        agg.drop(columns=[col], inplace=True)
        parts.append(agg)
    return pd.concat(parts, ignore_index=True)


def split_tables(agg_df, cocoa_min_year=2014):
    """Split into cocoa / territorial-emissions / territorial-deforestation tables."""
    cocoa = agg_df.drop(columns=TERRITORIAL_DEF + TERRITORIAL_EMISSIONS)
    terr_emission = agg_df.drop(columns=TERRITORIAL_DEF + COCOA_METRICS)
    terr_def = agg_df.drop(columns=TERRITORIAL_EMISSIONS + COCOA_METRICS)
    cocoa = cocoa[cocoa['YEAR'] >= cocoa_min_year]
    return {
        'c_def_emission': cocoa.dropna(),
        'emission': terr_emission.dropna(),
        'def': terr_def.dropna(),
    }


def reformat(input_dir, code, cocoa_min_year=2014):
    settings = COUNTRIES[code]
    merged = read_gee_files(input_dir, code, settings)
    wide = to_long_by_year(merged)
    agg = aggregate_spatial_levels(wide, settings['national_id'], settings['aggregate_prefix_lengths'])
    return split_tables(agg, cocoa_min_year)


def reshape_cocoa_area(path, code):
    """Section B export (one row per region, area in 'sum') -> REGION_ID, COCOA_HA."""
    settings = COUNTRIES[code]
    df = pd.read_csv(path)
    return pd.DataFrame({'REGION_ID': df[settings['region_column']].apply(settings['to_region_id']),
                         'COCOA_HA': df['sum']})


def reshape_cocoa_production(path, code):
    """Section C export (one row per region, one production_<year> column per
    year, region code in REGION_ID) -> REGION_ID, YEAR, COCOA_TONNES."""
    settings = COUNTRIES[code]
    df = pd.read_csv(path)
    year_cols = [c for c in df.columns if re.fullmatch(r'production_\d{4}', c)]
    long = df.melt(id_vars=['REGION_ID'], value_vars=year_cols, var_name='YEAR', value_name='COCOA_TONNES')
    long['YEAR'] = long['YEAR'].str[-4:].astype(int)
    long['REGION_ID'] = long['REGION_ID'].apply(settings['to_region_id'])
    return long.sort_values(['REGION_ID', 'YEAR']).reset_index(drop=True)


OUTPUT_FILES = {'c_def_emission': 'cocoa_deforestation_by_region.csv',
                'emission': 'territorial_emissions_by_region.csv',
                'def': 'territorial_deforestation_by_region.csv'}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--country', required=True, choices=sorted(COUNTRIES))
    p.add_argument('--input-dir', required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--cocoa-min-year', type=int, default=2014)
    p.add_argument('--cocoa-area-file', help='optional: the section B export (cocoa_area_...csv)')
    p.add_argument('--cocoa-production-file', help='optional: the section C export (cocoa_production_...csv)')
    a = p.parse_args()
    os.makedirs(a.output_dir, exist_ok=True)
    for name, table in reformat(a.input_dir, a.country, a.cocoa_min_year).items():
        out = os.path.join(a.output_dir, OUTPUT_FILES[name])
        table.to_csv(out, index=False)
        print("wrote", out, f"({len(table)} rows)")
    extras = [(a.cocoa_area_file, reshape_cocoa_area, 'cocoa_area_by_region.csv'),
              (a.cocoa_production_file, reshape_cocoa_production, 'cocoa_production_by_region.csv')]
    for path, fn, name in extras:
        if path:
            table = fn(path, a.country)
            out = os.path.join(a.output_dir, name)
            table.to_csv(out, index=False)
            print("wrote", out, f"({len(table)} rows)")


if __name__ == '__main__':
    main()
