"""
Turn a region boundary file into a zipped shapefile that can be uploaded to
Google Earth Engine (Assets tab > NEW > Shape files).

Usage (from the toolkit's top folder):
    python3 deforestation_metrics/prepare_regions_for_earth_engine.py <regions file> <output.zip>
Example:
    python3 deforestation_metrics/prepare_regions_for_earth_engine.py \
        data/synthetic_cote_divoire/regions/departments.geojson regions_for_earth_engine.zip

The file can be anything geopandas reads (GeoJSON, GeoPackage, shapefile...).
Boundaries are converted to longitude/latitude (EPSG:4326), and long column
names are kept short enough for the shapefile format (10 characters).
"""
import os
import sys
import tempfile
import zipfile

import geopandas as gpd


def main(src, out_zip):
    regions = gpd.read_file(src).to_crs(4326)
    too_long = [c for c in regions.columns if c != "geometry" and len(c) > 10]
    if too_long:
        print("These column names are longer than 10 characters and will be cut short:", too_long)
    with tempfile.TemporaryDirectory() as d:
        shp = os.path.join(d, "regions.shp")
        regions.to_file(shp)
        with zipfile.ZipFile(out_zip, "w") as z:
            for f in os.listdir(d):
                z.write(os.path.join(d, f), f)
    print(f"wrote {out_zip} ({len(regions)} regions). Columns: {[c for c in regions.columns if c != 'geometry']}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
