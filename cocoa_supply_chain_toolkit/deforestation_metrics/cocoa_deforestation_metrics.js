/*
=============================================================================
 COCOA DEFORESTATION METRICS (Google Earth Engine, JavaScript Code Editor)
=============================================================================
 Computes, for every sub-national region of a cocoa-producing country:

   - cocoa deforestation and degradation: area of undisturbed tropical moist
     forest lost (deforested OR degraded) and now under cocoa, annually and
     over an allocation period (default 15 years). Bands cd_*_tmf_loss_*.
   - cocoa deforestation CO2 emissions (deforestation only), gross and net (annual and allocation period)
   - territorial deforestation, degradation and remaining undisturbed forest
   - territorial deforestation CO2 emissions (gross)
   - cocoa area                                   (section B, optional)
   - cocoa production, allocated by suitability   (section C, optional)

 Each metric is exported as a CSV (one row per region, one column per year)
 to your Google Drive. deforestation_metrics/reshape_earth_engine_exports.py
 turns those CSVs into the tables used downstream.

 SECTIONS
   0. helpers (sum areas per region, export tables)
   A. forest loss, cocoa deforestation and degradation, emissions
   B. cocoa area per region (optional)
   C. cocoa production per region (optional)

 HOW TO USE
   1. Upload your region boundaries as an Earth Engine asset (a
      FeatureCollection with one feature per region and an ID property).
   2. Fill in CONFIG. Everything country-specific is there.
   3. Paste this file into the Code Editor and click Run, then start the
      export tasks in the Tasks tab.
   See docs/DEFORESTATION_METRICS.md for the method and for choosing a cocoa map.
=============================================================================
*/

// =============================================================================
// CONFIG: everything that changes between countries and updates
// =============================================================================
var CONFIG = {
  update: 'v1',                     // label used in export file names
  country_code: 'ci',               // short code used in export file names

  // Country outline (used to clip all layers)
  country: ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017')
             .filter(ee.Filter.eq('country_na', "Cote d'Ivoire")),
  // Sub-national regions the metrics are summed over. MUST match the regions
  // used in the supply-chain model (same IDs). Upload your own.
  regions: ee.FeatureCollection('users/<you>/region_boundaries'),   // TODO

  // Equal-area or national projected CRS used for the area calculation.
  // Côte d'Ivoire: EPSG:2041 (Abidjan 1987 / UTM zone 30N). For a new
  // country choose its official projected CRS (check before use).
  projection: ee.Projection('EPSG:2041'),

  // JRC Tropical Moist Forest dataset (Vancutsem et al. 2021); use the most
  // recent version that covers your last year.
  tmf_version: 'v1_2024',

  // Cocoa map: a BINARY image (1 = cocoa, 0 = not cocoa).
  // Côte d'Ivoire/Ghana: ETH Zurich map (Kalischek et al. 2023), probability
  // thresholded at 0.65. It covers ONLY Côte d'Ivoire and Ghana: for another
  // country you need a different map (see docs/DEFORESTATION_METRICS.md).
  cocoa_map: ee.Image('projects/ee-nk-cocoa/assets/cocoa_map_threshold_065'),

  // Years
  ap: 15,                // allocation period (years) for cocoa deforestation
  lag: 4,                // years between forest loss and cocoa production
  annual_lag: 4,         // lag for the ANNUAL cocoa deforestation metric:
                         // forest lost in year Y-4 is assigned to exports in Y
  terr_start: 2000,      // territorial metrics: first year
  terr_end: 2024,        //                      last year (≤ last TMF year)
  cocoa_start: 2014,     // cocoa metrics: first export year
  cocoa_end: 2024,       //                last export year. NB: with a cocoa map
                         // of 2019-2021, years after 2021 miss recent expansion,
                         // so report cocoa deforestation up to 2021 only.

  // Carbon
  // Above- and below-ground biomass carbon density (Soto-Navarro et al. 2020)
  carbon_density: ee.ImageCollection('WCMC/biomass_carbon_density/v1_0').first(),
  // CO2 stored in cocoa plantations incl. shade trees: (19 + 4) t C/ha x 3.67
  // = 84.41 t CO2/ha (Vervuurt et al. 2022). Subtracted to get NET emissions.
  C_COCOA_IND: 84.41,

  export_folder: 'cocoa_deforestation_metrics',  // Google Drive folder
  export_scale: 10                         // metres, for summing over regions
};

// =============================================================================
// 0. HELPERS
// =============================================================================
// region_reducer(): multiply each pixel by its area, convert m2 to hectares,
// and sum per region. export_table(): send a table to Google Drive.

/** Sum, per region, the area (ha) of pixels of each band (or band x value). */
function region_reducer(image, regions, scale) {
  return image.multiply(ee.Image.pixelArea())
              .divide(10000)                 // m2 -> ha
              .reduceRegions({
                collection: regions,
                reducer: ee.Reducer.sum(),
                scale: scale
              });
}

/** Export a FeatureCollection as CSV to Google Drive. */
function export_table(collection, name, folder) {
  Export.table.toDrive({
    collection: collection,
    description: name,
    folder: folder,
    fileFormat: 'CSV'
  });
}

// =============================================================================
// A. FOREST LOSS, COCOA DEFORESTATION AND EMISSIONS
// =============================================================================
var country = CONFIG.country;
var country_departments = CONFIG.regions;
var country_prj = CONFIG.projection;
var ap = CONFIG.ap, lag = CONFIG.lag;
var terr_start = CONFIG.terr_start, terr_end = CONFIG.terr_end;
var cocoa_start = CONFIG.cocoa_start, cocoa_end = CONFIG.cocoa_end;
var selectedCountry = CONFIG.country_code;

//------------------------ TMF LAYERS ----------------------------//
// AnnualChanges: land-cover class every December (1 = undisturbed forest,
// 2 = degraded, 3 = deforested, 4 = regrowth, 5 = water, 6 = other)
var ann = ee.ImageCollection('projects/JRC/TMF/' + CONFIG.tmf_version + '/AnnualChanges').mosaic().clip(country);
var def = ee.ImageCollection('projects/JRC/TMF/' + CONFIG.tmf_version + '/DeforestationYear').mosaic().clip(country);
var deg = ee.ImageCollection('projects/JRC/TMF/' + CONFIG.tmf_version + '/DegradationYear').mosaic().clip(country);

//------------------------ COCOA MAP ----------------------------//
var cocoa_eth2021 = CONFIG.cocoa_map.unmask(0).clip(country);

//------------------------ CARBON LAYERS ----------------------------//
var wcmc_raw = CONFIG.carbon_density.clip(country);
var wcmc = wcmc_raw.reproject(cocoa_eth2021.projection());   // to cocoa-map resolution
var C_COCOA_IND = ee.Number(CONFIG.C_COCOA_IND);

//------------------------ TERRITORIAL DEF AND DEG 1-YEAR ----------------------------//
// Per year: loss of undisturbed forest (any change), deforestation and degradation
function calculateUTMF_1year(ann, def, deg, startYear, endYear) {
  var result = ee.Image(1);
  for (var yr = startYear; yr <= endYear; yr++) {
    var prev = ann.select('Dec' + (yr - 1)).eq(1);
    var curr = ann.select('Dec' + yr);
    result = result
      .addBands(prev.neq(curr.eq(1)).rename('uTMF_1yr_lost_by_' + yr))
      .addBands(def.eq(yr).rename('uTMF_1yr_defo_by_' + yr))
      .addBands(deg.eq(yr).rename('uTMF_1yr_degr_by_' + yr));
  }
  return result.select(ee.List.sequence(1, (endYear - startYear + 1) * 3));
}

var terr_tmfloss_annual = calculateUTMF_1year(ann, def, deg, terr_start, terr_end);

//------------------------ YEARLY REMAINING UNDISTURBED TMF METRIC ----------------------------//
function calculateRemainingTMF(ann, startYear, endYear) {
  var result = ee.Image(1);
  for (var yr = startYear; yr <= endYear; yr++) {
    var yearTMF = ann.select('Dec' + (yr));
    result = result
      .addBands(yearTMF.eq(1).rename('uTMF_remaining' + yr));
  }
  return result.select(ee.List.sequence(1, (endYear - startYear + 1)));
}

var undisturbed_tmf_yearly = calculateRemainingTMF(ann, terr_start, terr_end);

//------------------------ COCOA FOREST IMPACT ----------------------------//
// For export year yr: forest that was undisturbed in (yr - lag - ap) and no
// longer undisturbed in (yr - lag), on land that the cocoa map shows as cocoa.
//   loss = any change from undisturbed (deforestation OR degradation)
//   defo = changed to deforested;  degr = changed to degraded
function calculateCocoaDeforestation(cocoaImage, startYear, endYear, ann, ap, lag) {
  var result = ee.Image(1);

  for (var yr = startYear; yr <= endYear; yr++) {
    var baseYear = yr - lag - ap;
    var targetYear = yr - lag;

    // Forest status in both years
    var base = ann.select('Dec' + baseYear).unmask(0);
    var target = ann.select('Dec' + targetYear).unmask(0);

    // Change detection
    var loss = base.eq(1).and(target.neq(1));
    var defo = base.eq(1).and(target.eq(3));
    var degr = base.eq(1).and(target.eq(2));

    // Cocoa attribution
    result = result
      .addBands(cocoaImage.and(loss).rename('cd_' + ap + 'yr_tmf_loss_' + yr))
      .addBands(cocoaImage.and(defo).rename('cd_' + ap + 'yr_tmf_def_' + yr))
      .addBands(cocoaImage.and(degr).rename('cd_' + ap + 'yr_tmf_deg_' + yr));
  }

  return result.select(ee.List.sequence(1, (endYear - startYear + 1) * 3));
}

// Allocation-period version: ap and lag from CONFIG. "Annual" version: the
// same function with ap = 1 and CONFIG.annual_lag.
var eth2021_c_tmfloss_total_ap_yr = calculateCocoaDeforestation(cocoa_eth2021, cocoa_start, cocoa_end, ann, ap, lag);
var eth2021_c_tmfloss_annual = calculateCocoaDeforestation(cocoa_eth2021, cocoa_start, cocoa_end, ann, 1, CONFIG.annual_lag);

// Generate a list of years
var cocoaYears = ee.List.sequence(cocoa_start, cocoa_end);
var territorialYears = ee.List.sequence(terr_start, terr_end);

// Helper function to generate band names
function makeBandNames(prefix, suffix, years) {
  return years.map(function(year) {
    return ee.String(prefix).cat(ee.Number(year).toInt().format()).cat(suffix || '');
  });
}

// Cocoa deforestation and degradation band names. 'loss' (not 'def') is the
// metric used downstream, because the definition includes degradation: shade
// trees in cocoa make many conversions show up as degradation.
var annCocoaBandNames = makeBandNames('cd_1yr_tmf_loss_','', cocoaYears);
var totalCocoaBandNames = makeBandNames('cd_' + ap + 'yr_tmf_loss_','', cocoaYears);

// Full deforestation bands (cocoa), used ONLY for emissions: there is no good
// way yet to account for emissions from degradation.
var annCocoaFullDefoBandNames = makeBandNames('cd_1yr_tmf_def_','', cocoaYears);
var totalCocoaFullDefoBandNames = makeBandNames('cd_' + ap + 'yr_tmf_def_','', cocoaYears);

// Deforestation band names (territory)
var annTerrDeforBandNames = makeBandNames('uTMF_1yr_defo_by_',  '', territorialYears);

var c_defor_emissions_input_apyr = eth2021_c_tmfloss_total_ap_yr.select(totalCocoaFullDefoBandNames);
var c_defor_emissions_input_1yr  = eth2021_c_tmfloss_annual.select(annCocoaFullDefoBandNames);

var terr_defor_1yr  = terr_tmfloss_annual.select(annTerrDeforBandNames);

//------------------------ EMISSIONS ----------------------------//
// gross = deforested pixel x carbon density (t C/ha) x 3.67 (C -> CO2)
// net   = gross - CO2 stored in cocoa plantations (floored at 0)
// AP and lag are already applied to the input image.
function calculateDeforestationEmissions(deforImage, wcmc, c_cocoa_ind, prefix) {

  // Get band names from deforImage
  var deforBands = deforImage.bandNames();

  // Extract years from band names (last 4 characters)
  var years = deforBands.map(function(name) {
    return ee.String(name).slice(-4);
  });

  // Step 1: Gross emissions (per year) with WCMC carbon density
  var ghgGross = deforImage
    .multiply(wcmc.unmask())
    .multiply(3.67) // Convert carbon to CO2
    .rename(years.map(function(year) {
      return ee.String('ghg_')
        .cat(prefix)
        .cat('_gross_')
        .cat(ee.Number.parse(year));
    }));

  // Step 2: Net emissions (gross - carbon stock in cocoa)
  // Note that net is not exported for territorial emissions, just cocoa
  var ghgNet = ghgGross
    .updateMask(ghgGross.gt(1)) // Mask insignificant values
    .subtract(c_cocoa_ind)
    .max(0)
    .rename(years.map(function(year) {
      return ee.String('ghg_')
      .cat(prefix)
      .cat('_net_')
      .cat(ee.Number.parse(year));
    }));

  return {
    net: ghgNet,
    gross: ghgGross
  };
}

var ghg_territorial_annual_results = calculateDeforestationEmissions(
  terr_defor_1yr, wcmc,
  C_COCOA_IND, // not used for territorial, just keeps the function signature
  'uTMF_def_1yr'
);
var ghg_cd_1yr_results = calculateDeforestationEmissions(
  c_defor_emissions_input_1yr, wcmc, C_COCOA_IND, 'cd_1yr');
var ghg_cd_apyr_results = calculateDeforestationEmissions(
  c_defor_emissions_input_apyr, wcmc, C_COCOA_IND, 'cd_' + ap + 'yr');

//------------------------ EXPORT TABLES ----------------------------//
function exportMetric(image, name, region, scale) {
  var reduced = region_reducer(image.reproject(country_prj, null, 30), region, scale);
  export_table(reduced, name, CONFIG.export_folder);
}

var s = CONFIG.export_scale;
exportMetric(eth2021_c_tmfloss_total_ap_yr, 'eth2021_cocoa_tmfloss_total_' + ap + 'yr_' + selectedCountry, country_departments, s);
exportMetric(eth2021_c_tmfloss_annual, 'eth2021_cocoa_tmfloss_annual_ha_' + selectedCountry, country_departments, s);
exportMetric(terr_tmfloss_annual, 'territorial_tmfloss_annual_ha_' + selectedCountry, country_departments, s);
exportMetric(ghg_cd_apyr_results.net, 'ghg_cd_net_' + ap + 'yr_' + selectedCountry, country_departments, s);
exportMetric(ghg_cd_apyr_results.gross, 'ghg_cd_gross_' + ap + 'yr_' + selectedCountry, country_departments, s);
exportMetric(ghg_cd_1yr_results.net, 'ghg_cd_net_1yr_' + selectedCountry, country_departments, s);
exportMetric(ghg_cd_1yr_results.gross, 'ghg_cd_gross_1yr_' + selectedCountry, country_departments, s);
exportMetric(ghg_territorial_annual_results.gross, 'ghg_territorial_gross_1yr_' + selectedCountry, country_departments, s);
exportMetric(undisturbed_tmf_yearly, 'undisturbed_tmf_yearly_' + selectedCountry, country_departments, s);

//------------------------ VISUALISATION ----------------------------//
Map.centerObject(country, 7);
Map.addLayer(cocoa_eth2021.selfMask(), {min: 0, max: 1, palette: 'white, green'}, 'Cocoa map', false);
Map.addLayer(terr_tmfloss_annual.updateMask(terr_tmfloss_annual), {min: 1, max: 1}, 'Territorial deforestation - annual', false);
Map.addLayer(eth2021_c_tmfloss_total_ap_yr.updateMask(eth2021_c_tmfloss_total_ap_yr), {min: 1, max: 1, palette: 'red'}, 'Cocoa deforestation - ' + ap + ' years', false);
Map.addLayer(eth2021_c_tmfloss_annual.updateMask(eth2021_c_tmfloss_annual), {min: 1, max: 1}, 'Cocoa deforestation - annual', false);


// =============================================================================
// B. COCOA AREA PER REGION (optional; set RUN_COCOA_AREA = true)
// =============================================================================
// Hectares under cocoa per region, from the cocoa map.
var RUN_COCOA_AREA = false;
if (RUN_COCOA_AREA) {
  var cocoa_map_area = CONFIG.cocoa_map.unmask();
  export_table(region_reducer(cocoa_map_area, CONFIG.regions, CONFIG.export_scale),
               'cocoa_area_' + selectedCountry + '_' + CONFIG.update,
               CONFIG.export_folder);
}


// =============================================================================
// C. COCOA PRODUCTION PER REGION (optional; set RUN_PRODUCTION = true)
// =============================================================================
// Distributes national production (e.g. ICCO statistics) across regions in
// proportion to "suitable cocoa": cocoa-map pixels weighted by a cocoa
// suitability layer (0-100%), e.g. the cocoa suitability map of Schroth et
// al. (2016) uploaded as your own asset.
var RUN_PRODUCTION = false;
var PRODUCTION = {
  suitability: null,   // e.g. ee.Image('users/<you>/cocoa_suitability'), values 0-100
  // national production, tonnes per year (Côte d'Ivoire figures from ICCO)
  national_tonnes: {2019: 2154000, 2020: 2105000, 2021: 2248000,
                    2022: 2121000, 2023: 2241000, 2024: 1674000},
  region_id_property: 'LVL_4_CODE'
};
if (RUN_PRODUCTION) {
  var cocoa_map = CONFIG.cocoa_map;
  // the suitability layer is given in percentages (0-100%), rescale to 0-1
  var suitability = PRODUCTION.suitability.divide(100);
  // multiply the cocoa_map by the suitability to get relative suitable cocoa
  var suitablecocoa = cocoa_map.multiply(suitability);

  // Sum of suitable cocoa per region, and for the whole country
  var department_suitability = suitablecocoa.multiply(ee.Image(1))
                                    .reduceRegions({reducer: ee.Reducer.sum(),
                                                    collection: CONFIG.regions,
                                                    scale: 30});
  var country_suitability = suitablecocoa.multiply(ee.Image(1))
                                    .reduceRegions({reducer: ee.Reducer.sum(),
                                                    collection: CONFIG.regions.union(),
                                                    scale: 30})
                                    .first().get('sum');

  // region production = (region suitable cocoa / country suitable cocoa) x national production
  var production_per_department = function(feature) {
    var share = ee.Number(feature.get('sum')).divide(ee.Number(country_suitability));
    var props = {REGION_ID: feature.get(PRODUCTION.region_id_property)};
    Object.keys(PRODUCTION.national_tonnes).forEach(function(year) {
      props['production_' + year] = share.multiply(PRODUCTION.national_tonnes[year]);
    });
    return feature.set(props).setGeometry(null);
  };

  export_table(department_suitability.map(production_per_department),
               'cocoa_production_' + selectedCountry + '_' + CONFIG.update,
               CONFIG.export_folder);
}
