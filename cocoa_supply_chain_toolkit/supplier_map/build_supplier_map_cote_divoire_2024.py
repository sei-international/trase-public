"""
build_supplier_map_cote_divoire_2024.py
=======================================
Builds the Côte d'Ivoire 2024 supplier map (which cooperatives exist, where
they are, and which companies buy from them) from the companies' published
supplier lists. This is the worked example for docs/NEW_COUNTRY_GUIDE.md,
step 2; the reusable parts are in supplier_map_tools.py.

The four steps run in order. Each one writes its result to a file, so you can
stop, check the file by hand, and carry on from the next step:

  step 1  read each company's disclosure (PDF tables, Excel files, scraped
          maps) and reshape them all into one column format
  step 2  combine the company files, keep Côte d'Ivoire rows, and align the
          columns with last year's supplier map
  step 3  clean names, match cooperatives to last year's map, assign each
          cooperative to a department, and mark which companies are traders
  step 4  fill gaps from last year's map, estimate farmer numbers, and write
          the two supplier tables the model reads
  step 5  convert them to the standard format (docs/INPUT_DATA.md, and the
          spreadsheet template in supplier_map/templates/)

Many lines are corrections for specific companies or cooperatives in the 2024
disclosures. They show the kind of decisions you will need to make; they do
not apply to another country or year.

Folders (all under --data-dir, default: the synthetic raw inputs in
data/synthetic_raw_inputs/, made by data/make_synthetic_raw_inputs.py):
  supplier_map/company_disclosures_2024/  the companies' disclosures as downloaded
  supplier_map/last_year/                 last year's supplier map and disclosures
  supplier_map/work/                      intermediate files, one or more per step
  supplier_map/                           the two tables the model reads

Usage:
  python supplier_map/build_supplier_map_cote_divoire_2024.py --data-dir <folder>
  python supplier_map/build_supplier_map_cote_divoire_2024.py --data-dir <folder> --from-step 4

With the synthetic raw inputs, every step runs, but the fake disclosures are
much smaller and simpler than the real ones: some checks print empty tables,
and the result means nothing.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # for supplier_map_tools


def step1_standardise_disclosures(DATA_DIR):
    """Read each company's supplier disclosure and reshape them all into one column format."""
    # Aiming for this format:
    #
    # COMPANY;DISCL_COUNTRY_NAME;DISCL_TRADER_NAME;DISCL_AREA_NAME;DISCL_SUPPLIER_ABRVNAME;DISCL_SUPPLIER_FULLNAME;DISCL_SUPPLIER_TYPE;DISCL_LONGITUDE;DISCL_LATITUDE;DISCL_YEAR;DISCL_NUMBER_FARMERS;DISCL_VOLUMES;DISCL_VOLUMES_UNIT;DISCL_CERTIFICATION_NAME;DISCL_CERTIFICATION_PCT;DISTRICT_NAME;DISTRICT_GEOCODE;LOCALITY_NAME;TRADER_NAME;CAM_BUYERS;IS_CAM_V3;IS_JRC;JRC_BUYER_ID
    # CARGILL;IVORY_COAST;NA;NA;S.O.C.O.N.A.VA-COOP-CA;NA;COOPERATIVE;-6.452173099938271;6.875132237998441;2020;581;NA;NA;"CARGILL COCOA PROMISE; UTZ";NA;NA;NA;NA;NA;NA;FALSE;NA;NA

    # can take coordinates from previous years disclosures (filter for CIV)
    #
    # <DATA_DIR>/supplier_map/last_year/company_disclosures_2023.csv


    headings = ["COMPANY","DISCL_COUNTRY_NAME","DISCL_TRADER_NAME","DISCL_AREA_NAME",
                "DISCL_SUPPLIER_ABRVNAME","DISCL_SUPPLIER_FULLNAME","DISCL_SUPPLIER_TYPE",
                "DISCL_LONGITUDE","DISCL_LATITUDE","DISCL_YEAR",
                "DISCL_NUMBER_FARMERS","DISCL_VOLUMES","DISCL_VOLUMES_UNIT",
                "DISCL_CERTIFICATION_NAME","DISCL_CERTIFICATION_PCT","DISTRICT_NAME",
                "DISTRICT_GEOCODE","LOCALITY_NAME","TRADER_NAME","CAM_BUYERS","IS_CAM_V3","IS_JRC","JRC_BUYER_ID"]

    # # Scraped maps

    # function for use with Touton scraped data

    import re

    def extract_cooperative_data(data_string):
        """
        Extracts cooperative names and coordinates from the provided data string.

        Args:
            data_string: A string containing the cooperative data.

        Returns:
            A list of dictionaries, where each dictionary represents a cooperative
            and contains its name and coordinates.
        """
        # Regex to find all coordinate pairs (latitude, longitude)
        coordinates_regex = re.compile(r'\[null,\[(-?\d+\.\d+),(-?\d+\.\d+.*?)\]\]')

        # Regex to find all cooperative names
        names_regex = re.compile(r'\[\[\"([A-Z0-9\.\s-]+)\"\]\]')

        # Find all matches for coordinates and names
        coordinates = coordinates_regex.findall(data_string)
        names = names_regex.findall(data_string)

        # Combine the names and coordinates into a list of dictionaries
        cooperatives = []
        for name, (lat, lon) in zip(names, coordinates):
            cooperatives.append({
                "DISCL_SUPPLIER_ABRVNAME": name,
                "DISCL_LATITUDE": float(lat),
                "DISCL_LONGITUDE": float(lon)
            })

        return cooperatives

    import ast
    import pandas as pd

    fp = f"{DATA_DIR}/supplier_map/company_disclosures_2024/scraped_map/blommer_map_scraped.txt"

    with open(fp, "r") as file:
        text = file.read()

    data_list = ast.literal_eval(text)

    columns = [
        "DISCL_COUNTRY_NAME",
        "DISCL_TRADER_NAME",
        "DISCL_SUPPLIER_ABRVNAME",
        "DISCL_AREA_NAME",
        "DISCL_LATITUDE",
        "DISCL_LONGITUDE"
    ]

    # Build a list of dicts for each row
    rows = []
    for data in data_list:
        rows.append({
            "DISCL_COUNTRY_NAME": data[6],
            "DISCL_TRADER_NAME": data[7],
            "DISCL_SUPPLIER_ABRVNAME": data[8],
            "DISCL_AREA_NAME": data[9],
            "DISCL_LATITUDE": data[10],
            "DISCL_LONGITUDE": data[11]
        })

    big_df = pd.DataFrame(rows, columns=columns)
    big_df["DISCL_YEAR"] = 2024
    big_df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    big_df["COMPANY"] = "Blommer Chocolate Company"

    big_df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_blommer.csv", index=False)

    import ast
    import pandas as pd
    import re

    fp = f"{DATA_DIR}/supplier_map/company_disclosures_2024/scraped_map/touton_map_scraped.txt"

    with open(fp, "r") as file:
        text = file.read()

    text = text.replace('\\', '')  # Remove backslashes
    text = text.replace('[,', '') 
    text = re.sub(r'\\u[0-9a-fA-F]{4}', '', text)  # Remove unicode escapes
    text = text.replace('null', 'None')


    print(text) 
    # Convert text to Python object
    data = ast.literal_eval(text)

    # The list of coops is the third element (index 2) in the outer list
    coops = data[2]

    results = []
    for coop in coops:
        # Each coop: [[], null, 1, 1, [[null, [lat, lon]], ...], ...], [[["COOP NAME"]]]]

        coords = coop[4][0][1]  # [lat, lon]
        name = coop[5][0][0][0] # "COOP NAME"
        results.append((name, coords[0], coords[1]))


    # Print results
    for name, lat, lon in results:
        print(f"{name}, {lat},{lon}")

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/scraped_map/touton_map_as_csv.csv")

    columns = [
        "DISCL_COUNTRY_NAME",
        "DISCL_TRADER_NAME",
        "DISCL_SUPPLIER_ABRVNAME",
        "DISCL_AREA_NAME",
        "DISCL_LATITUDE",
        "DISCL_LONGITUDE"
    ]

    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "Touton"
    df["COUNTRY"] = "Ivory Coast"

    df.rename(columns={
        "Cooperative Name": "DISCL_SUPPLIER_ABRVNAME",
        "Location": "DISCL_AREA_NAME",
        "Latitude": "DISCL_LATITUDE",
        "Longitude": "DISCL_LONGITUDE",
        "Number of Farmers": "DISCL_NUMBER_FARMERS",
    }, inplace=True)

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_touton.csv", index=False)

    import geopandas as gpd

    df = gpd.read_file(f"{DATA_DIR}/supplier_map/company_disclosures_2024/scraped_map/cargill_coops_2324.geojson")

    df.year_joined.max()

    df["YEAR"] = 2024
    df["COMPANY"] = "Cargill"
    df.rename(columns={
        "coop_name": "DISCL_SUPPLIER_ABRVNAME",
        "gps_lat": "DISCL_LATITUDE",
        "gps_long": "DISCL_LONGITUDE",
        "country": "COUNTRY",
        "certificat": "DISCL_CERTIFICATION_NAME",
        "f__certifi": "DISCL_CERTIFICATION_PCT",
        "location_t": "DISCL_SUPPLIER_TYPE"    
    }, inplace=True)    

    df.drop(columns=["year_joine", "geometry", "objectid"], inplace=True)

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_cargill.csv", index=False)

    # # Tabula outputs

    df= pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/tabula_outputs/tabula-cote-d-ivoire-ofi-sustainable-cocoa-suppliers-2023-and-2024.csv")

    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "OFI"
    df["COUNTRY"] = "Ivory Coast"
    df["DISCL_SUPPLIER_ABRVNAME"] = df["Farmer Group"]
    df["DISCL_AREA_NAME"] = df["Location"]
    df.drop(columns=["No","Farmer Group", "Location"], inplace=True)

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_OFI.csv", index=False)

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/tabula_outputs/ecom/ecom_CIV.csv")

    df.rename(columns={
        "Cooperative Name": "DISCL_SUPPLIER_ABRVNAME",
        "Region": "DISTRICT_NAME",
        "Full Name": "DISCL_SUPPLIER_FULLNAME"
    }, inplace=True)

    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "ECOM"
    df["COUNTRY"] = "Ivory Coast"

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_ecom.csv", index=False)

    df= pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/tabula_outputs/tabula-etg 2024.csv")
    df.rename(columns={
        "Country": "COUNTRY",
        "Supplier Name": "DISCL_SUPPLIER_ABRVNAME",
        "Latitude": "DISCL_LATITUDE",
        "Longitude": "DISCL_LONGITUDE"
    }, inplace=True)

    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "ETG"

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_etg.csv", index=False)

    df= pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/tabula_outputs/tabula-ferrero-cocoa-suppliers-list-23-24.csv")

    df.rename(columns={
        "LOCATION ORIGIN": "COUNTRY",
        "FARMER GROUP": "DISCL_SUPPLIER_ABRVNAME",
        "FULL NAME": "DISCL_SUPPLIER_FULLNAME",
        "MAIN CITY": "DISCL_AREA_NAME"
    }, inplace=True)

    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "FERRERO"

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_ferrero.csv", index=False)

    df= pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/tabula_outputs/tabula-2023 T2 MARS COCOA SUPPLY CHAIN DISCLOSURE -Jan 2024 FINAL-3.csv")

    df.drop(columns=["INDEX"], inplace=True)

    df["DISCL_YEAR"] = 2023
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "MARS"

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2023_mars_fromlist.csv", index=False)

    df= pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/tabula_outputs/tabula-nestle_2025_responsible-sourcing-disclosure-cocoa.csv")

    df.drop(columns=["Intermediary Supplier Location (Country)"], inplace=True)
    df.rename(columns={
        "Country of Origin": "COUNTRY",
        "Intermediary Supplier": "DISCL_SUPPLIER_ABRVNAME",
        "Direct Supplier": "DISCL_TRADER_NAME",
        "Type": "DISCL_SUPPLIER_TYPE"
    }, inplace=True)

    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "NESTLE"
    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_nestle.csv", index=False)

    import pandas as pd
    import re

    data = []
    with open(f'{DATA_DIR}/supplier_map/company_disclosures_2024/scraped_map/whittakers_scraped_map.txt', 'r', encoding='utf-8') as f:
        for line in f:
            # Remove whitespace and skip empty lines
            line = line.strip()
            if not line:
                continue
            # Extract key-value pairs using regex
            matches = re.findall(r'(\w+)=["]?([^" ]*)["]?', line)
            row = {k: v for k, v in matches}
            # Also extract :key="value" pairs
            matches_colon = re.findall(r':(\w+)="([^"]*)"', line)
            for k, v in matches_colon:
                row[k] = v
            data.append(row)

    df = pd.DataFrame(data)
    df['growers'] = pd.to_numeric(df['growers'], errors='coerce')
    df['harvest'] = df['harvest'].apply(lambda x: x.replace(',', ''))
    df['harvest'] = pd.to_numeric(df['harvest'], errors='coerce')
    print(df)

    villages_per_op = df.groupby('op')['village'].apply(list)
    print(villages_per_op)

    import numpy as np

    names = ['Asankrangwa', 'Tarkwa-Huni', 'Assin']
    villages_lists = [villages_per_op['Asankrangwa'], villages_per_op['Tarkwa-Huni'], villages_per_op['Assin']]
    out_df = pd.DataFrame({
        "DISCL_SUPPLIER_ABRVNAME": names,
        "DISCL_NUMBER_FARMERS":[633, 881, 882],
        "DISCL_VOLUMES":[654092, np.nan, 918489],
        "DISCL_AREA_NAME": villages_lists,
        "DISCL_YEAR": 2023,
        "COUNTRY": "Côte d'Ivoire",
        "DISCL_SUPPLIER_TYPE": "Cooperative",
        "COMPANY": "WHITTAKERS",
        "DISCL_VOLUMES_UNIT": "kg"

    })

    # columns=["DISCL_AREA_NAME",

    out_df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2023_whittakers.csv", index=False)

    # # Text

    df = pd.DataFrame()

    df["DISCL_SUPPLIER_ABRVNAME"] = ["COODID", "DAKUA", "ECAKOOG", "NA"]
    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "GODIVA"
    df["TRADER"] = ["ONEM", "ONEM", "ONEM", "BARRY CALLEBUT"]
    df["COUNTRY"] = "Ivory Coast"

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_godiva.csv", index=False)

    df = pd.DataFrame()

    df["DISCL_SUPPLIER_ABRVNAME"] = ["SCOOPAG", "DAKUA", "COODIG", "CAPUM"]
    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "ONEM"
    df["COUNTRY"] = "Ivory Coast"

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_onem.csv", index=False)

    df = pd.DataFrame(columns=['DISCL_AREA_NAME', 'LOCALITY_NAME'])
    df['DISCL_SUPPLIER_ABRVNAME'] = ['SCOOWEND', 'SCAGB' , 'SOCASS', 'SCAK ', 'SOCAGRI2' , 'CAGNAN', 
                                      'SCANG', 'SCAPD' , 'SOCOAMO' , 'SOCAT' , 'SCANFI', 'SCOOPAGED' , 'CAEHS', 
                                      'SCOOPNAG', 'SCAMED' , 'CAFUGO' , 'ECSP' , 'CAMAYE' , 'SOCAMEA', 'ECAKOOG']
    df["COMPANY"] = "PURATOS"
    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COUNTRY"] = "Ivory Coast"

    df['DISCL_SUPPLIER_FULLNAME'] = ['Société Cooperative Wend Bark',
    'Société Coopérative Agricole de Gbagbam',
    'Société Coopérative Agricole Sabary de Sago',
    'Société Cooperative Agricole de Fatouakro',
    'Société Coopérative Agricole De Grihiri 2',
    'Société Agricole de Gnanpoadji',
    'Societe Agricole de Grabo',
    'Societe Cooperative Agricole Des Producteurs De Dogbo',
    'Société Coopérative Agricole de Monogaga Carrefour',
    'Société Agricole Cooperative de Tabou',
    'Société Cooperative Agricole Niamkey Et Famille De L’Indenie',
    'Societé Cooperative Garo est Divo',
    'Coopérative Agricole Ety-Ewoun-Anien du Haut Sassandra',
    'Société Coopérative des Nouveaux Agriculteurs de Gueyo',
    'Société cooperative Agricole pour la maitrise de l’entraide durable',
    'Societé Cooperative des Freres Unis Gobroko',
    'Entreprise Cooperative de Saint Paul',
    'Camayé Cooperative',
    'SOCIETE COOPERATIVE MAN EDI ANOUANZE',
    'Coopérative Agricole Koognanan de Grogouya en Abrégé']

    df.loc[df['DISCL_SUPPLIER_ABRVNAME'] == 'CAMAYE', 'LOCALITY_NAME'] = 'Abengourou'
    df.loc[df['DISCL_SUPPLIER_ABRVNAME'] == 'CAMAYE', 'DISCL_AREA_NAME'] = 'Region du Juablin'

    df.loc[df['DISCL_SUPPLIER_ABRVNAME'] == 'SOCAMEA', 'LOCALITY_NAME'] = 'Man'
    df.loc[df['DISCL_SUPPLIER_ABRVNAME'] == 'SOCAMEA', 'DISCL_AREA_NAME'] = 'Region des Montagnes'

    df.loc[df['DISCL_SUPPLIER_ABRVNAME'] == 'ECAKOOG', 'LOCALITY_NAME'] = 'Lakota'
    df.loc[df['DISCL_SUPPLIER_ABRVNAME'] == 'ECAKOOG', 'DISCL_AREA_NAME'] = 'Region du Loh-Djiboua'

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_puratos.csv", index=False)

    df = pd.DataFrame()

    df["DISCL_SUPPLIER_ABRVNAME"] = ["CAPEDIG (part of ECOOKIM)"]
    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COMPANY"] = "VALRHONA"
    df["DISCL_AREA_NAME"]  = "Dibobly, Guémon"
    df["DISCL_LATITUDE"] = 6.742222
    df["DISCL_LONGITUDE"] = -7.012278
    df["COUNTRY"] = "Ivory Coast"

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_valrhona.csv", index=False)

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_ritter_sport.csv")

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/excel/2024_transparance.csv")

    df.rename(columns={
        "SUPPLIER": "DISCL_SUPPLIER_ABRVNAME",
        "LOCATION": "DISCL_AREA_NAME"
    }, inplace=True)

    df.drop(columns=["N"], inplace=True)
    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_transparance.csv", index=False)

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/excel/2024_lindt_sprungli.csv")

    df.rename(columns={
        "Country": "DISCL_COUNTRY",
        "Tier 2 Supplier": "DISCL_TRADER_NAME",
        "Tier 1 Supplier": "TRADER_NAME",
        "Farmer Group/District": "DISCL_SUPPLIER_ABRVNAME",
        "Location": "DISCL_AREA_NAME"
    }, inplace=True)

    df = df[df.DISCL_COUNTRY=="Côte d'Ivoire"]
    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_lindt_sprungli.csv", index=False)

    import pandas as pd
    import numpy as np

    df = pd.read_excel(f"{DATA_DIR}/supplier_map/company_disclosures_2024/excel/alter_eco_sourcing_2018-2024.xlsx")

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_alter_eco.csv", index=False)

    # format tonys info

    headings = ["COMPANY","DISCL_COUNTRY_NAME","DISCL_TRADER_NAME","DISCL_AREA_NAME",
                "DISCL_SUPPLIER_ABRVNAME","DISCL_SUPPLIER_FULLNAME","DISCL_SUPPLIER_TYPE",
                "DISCL_LONGITUDE","DISCL_LATITUDE","DISCL_YEAR",
                "DISCL_NUMBER_FARMERS","DISCL_VOLUMES","DISCL_VOLUMES_UNIT",
                "DISCL_CERTIFICATION_NAME","DISCL_CERTIFICATION_PCT","DISTRICT_NAME",
                "DISTRICT_GEOCODE","LOCALITY_NAME","TRADER_NAME","CAM_BUYERS","IS_CAM_V3","IS_JRC","JRC_BUYER_ID"]

    df = pd.DataFrame()

    df['DISCL_SUPPLIER_ABRVNAME']=['ABOCFA', 'ASETENAPA', 'Asunafo', 'COOBADI', 'COOPAZA', 'CAYAT', 'ECAM', 'ECOJAD', 'ESCOPAG', 'KAPATCHIVA', 'SOCOOPACDI', 'Kukuom', 'DJOUMAN', 'SOCASIB', 'SICOPAG', 'SCAWOD', 'AHONTO', 'SOCADA', 'SOCA2PD']
    df["COMPANY"] = "TONYS CHOCOLONELY"
    df["DISCL_YEAR"] = 2024
    df["DISCL_SUPPLIER_TYPE"] = "Cooperative"
    df["COUNTRY"] = "Côte d'Ivoire"
    df["DISCL_TRADER_NAME"] = [["Ocean", "Ecookim", "Barry Callebaut", "Baronie", "Cemoi"]]*len(df['DISCL_SUPPLIER_ABRVNAME'])

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_by_company/2024_tonys_chocolonely.csv", index=False)

    import os
    import pandas as pd

    # Define the folder path
    folder_path = f'{DATA_DIR}/supplier_map/work/step1_by_company/'

    # Initialize an empty list to store DataFrames
    dataframes = []

    # Iterate through each file in the folder
    for fn in os.listdir(folder_path):
        print(fn)
        if fn.endswith('.csv'):  # Check if the file is a CSV
            file_path = os.path.join(folder_path, fn)
            df = pd.read_csv(file_path)  # Read the CSV into a DataFrame
            dataframes.append(df)  # Append the DataFrame to the list

    # Combine all DataFrames vertically, aligning columns
    combined_df = pd.concat(dataframes, ignore_index=True)
    combined_df['DISCL_COUNTRY'].replace("Ivory Coast", "Côte d'Ivoire", inplace=True)

    # Display the combined DataFrame
    print(combined_df)

    combined_df.to_csv(f"{DATA_DIR}/supplier_map/work/step1_all_companies.csv", index=False)


def step2_combine_and_align_columns(DATA_DIR):
    """Combine the company files, keep Côte d'Ivoire rows, align columns with last year's map."""
    import pandas as pd
    import numpy as np

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step1_all_companies.csv")

    df = df.copy()

    print(df.shape)

    # copy over value from DISCL_COUNTRY_NAME where DISCL_COUNTRY is NaN and vice versa
    mask1 = df['DISCL_COUNTRY'].isna() & df['DISCL_COUNTRY_NAME'].notna()
    df.loc[mask1, 'DISCL_COUNTRY'] = df.loc[mask1, 'DISCL_COUNTRY_NAME']

    mask2 = df['DISCL_COUNTRY_NAME'].isna() & df['DISCL_COUNTRY'].notna()
    df.loc[mask2, 'DISCL_COUNTRY_NAME'] = df.loc[mask2, 'DISCL_COUNTRY']


    mask = (df['DISCL_COUNTRY'].isin(["Côte d'Ivoire", " Ivory Coast", "Cote d'Ivoire", np.nan])) | \
           (df['DISCL_COUNTRY_NAME'].isin(["IVORY COAST", "CIV", np.nan])) | \
                  (df['COUNTRY'].isin([np.nan, "Cote d'Ivoire", 'Ivory Coast', "Côte d'Ivoire",'CÔTE D’IVOIRE', 'CIV'])) | \
                  (df['COUNTRY_NAME'].isin([np.nan, "IVORY COAST"]))
    df = df[mask].copy()                  # avoid SettingWithCopyWarning

    print(df.shape)

    import pandas as pd
    import numpy as np
    import unicodedata

    # prefer keeping df as a copy when mutating
    df = df.copy()

    # columns involved (adjust names if you have slightly different names/casing)
    cols = ['COUNTRY', 'DISCL_COUNTRY', 'DISCL_COUNTRY_NAME', 'COUNTRY_NAME']

    # 1) Normalise empty strings -> NA across these columns
    df[cols] = df[cols].replace(r'^\s*$', pd.NA, regex=True)

    # 2) Build COUNTRY by taking the first non-null value in the preferred order:
    #    (this is vectorised and fast)
    df['COUNTRY'] = df[cols].bfill(axis=1).iloc[:, 0]

    # 3) Optional normalisation: strip, remove accents, uppercase
    def normalize_country(val):
        if pd.isna(val):
            return val
        s = str(val).strip()
        # remove accents (Côte -> Cote) and force ASCII
        s = unicodedata.normalize('NFKD', s).encode('ASCII', 'ignore').decode('ASCII')
        return s.upper()

    df['COUNTRY'] = df['COUNTRY'].apply(normalize_country)

    # 4) Drop the other country columns (keep only df['COUNTRY'])
    df.drop(columns=['DISCL_COUNTRY', 'DISCL_COUNTRY_NAME', 'COUNTRY_NAME'], inplace=True)

    # Quick checks
    print("shape:", df.shape)
    print("COUNTRY value counts (top):")
    print(df['COUNTRY'].value_counts(dropna=False).head(10))

    df = df[df.COUNTRY.isin(["IVORY COAST", "COTE D'IVOIRE", "CIV", "COTE DIVOIRE", np.nan])].copy()

    df['COUNTRY'] = "IVORY_COAST"

    import pandas as pd

    # copy if you want to keep original
    df = df.copy()

    # Uppercase every cell only when it's a str (preserves NaN, numbers, lists, dicts, ...)
    df = df.map(lambda v: v.upper() if isinstance(v, str) else v)

    # Uppercase column names (still vectorised)
    df.columns = df.columns.map(lambda c: c.upper() if isinstance(c, str) else c)

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step2_cote_divoire_rows.csv", index=False)

    # Standardise names in text

    # Decide which values should be under which columns

    # Impute missing values using 2023 dataset 

    df_2023 = pd.read_csv(f'{DATA_DIR}/supplier_map/last_year/company_disclosures_2023.csv', sep=';')

    # How were traders and other disclosing companies handled last year?

    print(df_2023.COMPANY.unique())

    print(df_2023.DISCL_TRADER_NAME.unique())

    import pandas as pd

    df = pd.read_csv(f'{DATA_DIR}/supplier_map/work/step2_cote_divoire_rows.csv')

    df_2024_cols_ordered = ['TRADER_NAME', 'TRADER', 'DISCL_TRADER_NAME', # combined below into 'DISCL_TRADER_NAME'
     'COMPANY', 
            'YEAR', ' DISCL_YEAR', 'DISCL_YEAR', # combined below into 'DISCL_YEAR'
            'DISCL_LONGITUDE', 'DISCL_LATITUDE', 'LATITUDE', 'LONGITUDE', # combined below into 'DISCL_LATITUDE' and 'DISCL_LONGITUDE'
           'SUPPLIER_ABRVNAME', 'SUPPLIER_FULLNAME', 'DISCL_SUPPLIER_ABRVNAME', 'DISCL_SUPPLIER_NAME', 'DISCL_SUPPLIER_FULLNAME', # combined below into 'DISCL_SUPPLIER_ABRVNAME' and 'DISCL_SUPPLIER_FULLNAME'
           'DISCL_AREA_NAME', 'LOCALITY_NAME', 'DISTRICT_GEOCODE', 'DISTRICT_NAME', # combined below into 'DISCL_AREA_NAME' and 'DISTRICT_GEOCODE'
                   'TYPE', 'DISCL_SUPPLIER_TYPE', ' DISCL_SUPPLIER_TYPE', # combined below into 'DISCL_SUPPLIER_TYPE'
           'DISCL_CERTIFICATION_NAME', 'DISCL_CERTIFICATION_PCT',
           'DISCL_NUMBER_FARMERS',
            'COUNTRY', # renamed below to DISCL_COUNTRY_NAME
           'INDEX', # dropped below
           'DISCL_VOLUMES','DISCL_VOLUMES_UNIT',  
           'CAM_BUYERS', 'IS_CAM_V3', 'IS_JRC', 'JRC_BUYER_ID']

    df_2023_columns_ordered = ['DISCL_TRADER_NAME', 'TRADER_NAME', 
                               'COMPANY', 
                            'DISCL_YEAR', 
                            'DISCL_LONGITUDE', 'DISCL_LATITUDE',
                            'DISCL_SUPPLIER_ABRVNAME', 'DISCL_SUPPLIER_FULLNAME',
                               'DISCL_AREA_NAME','LOCALITY_NAME', 'DISTRICT_GEOCODE', 'DISTRICT_NAME',
           'DISCL_SUPPLIER_TYPE', 
           'DISCL_CERTIFICATION_NAME', 'DISCL_CERTIFICATION_PCT',
           'DISCL_NUMBER_FARMERS', 
           'DISCL_COUNTRY_NAME', 

           'DISCL_VOLUMES','DISCL_VOLUMES_UNIT', 
            'CAM_BUYERS', 'IS_CAM_V3', 'IS_JRC','JRC_BUYER_ID']

    # Discern difference between similar columns

    print(df_2023['TRADER_NAME'].unique())
    print(df_2023['DISCL_TRADER_NAME'].unique())

    print(df_2023['DISCL_AREA_NAME'].unique())
    print(df_2023['LOCALITY_NAME'].unique())
    print(df_2023['DISTRICT_NAME'].unique())
    print(df_2023['DISTRICT_GEOCODE'].unique())

    # Make 2024 columns match 2023 columns

    df.rename(columns={'COUNTRY': 'DISCL_COUNTRY_NAME'}, inplace=True)

    # combined below into 'DISCL_TRADER_NAME'

    # Where 'DISCL_TRADER_NAME' is NaN, copy over 'TRADER_NAME'
    mask = df['DISCL_TRADER_NAME'].isna() & df['TRADER_NAME'].notna()
    df.loc[mask, 'DISCL_TRADER_NAME'] = df.loc[mask, 'TRADER_NAME']

    # Where 'DISCL_TRADER_NAME' is NaN, copy over 'TRADER'
    mask = df['DISCL_TRADER_NAME'].isna() & df['TRADER'].notna()
    df.loc[mask, 'DISCL_TRADER_NAME'] = df.loc[mask, 'TRADER']

    # Where 'COMPANY' is NaN, copy over 'TRADER_NAME'
    mask = df.COMPANY.isna()&df.TRADER_NAME.notna()
    df.loc[mask, 'COMPANY'] = df.loc[mask, 'TRADER_NAME']

    df.drop(columns=['TRADER_NAME', 'TRADER'], inplace=True)

    df.drop(columns=['INDEX'], inplace=True)

    # combined below into 'DISCL_YEAR'

    # Where 'DISCL_YEAR is NaN, copy over ' DISCL_YEAR'
    mask = df['DISCL_YEAR'].isna() & df[' DISCL_YEAR'].notna()
    df.loc[mask, 'DISCL_YEAR'] = df.loc[mask, ' DISCL_YEAR']

    # Where 'DISCL_YEAR' is NaN, copy over 'YEAR'
    mask = df['DISCL_YEAR'].isna() & df['YEAR'].notna()
    df.loc[mask, 'DISCL_YEAR'] = df.loc[mask, 'YEAR']

    print(df[df.DISCL_YEAR.isna() & df[' DISCL_YEAR'].notna()])
    print(df[df.DISCL_YEAR.isna() & df['YEAR'].notna()])

    df.drop(columns=[' DISCL_YEAR', 'YEAR'], inplace=True)

    # combined below into 'DISCL_LATITUDE' and 'DISCL_LONGITUDE'

    mask = df['DISCL_LATITUDE'].isna() & df['LATITUDE'].notna()
    df.loc[mask, 'DISCL_LATITUDE'] = df.loc[mask, 'LATITUDE']

    mask = df['DISCL_LONGITUDE'].isna() & df['LONGITUDE'].notna()
    df.loc[mask, 'DISCL_LONGITUDE'] = df.loc[mask, 'LONGITUDE']

    df.drop(columns=['LATITUDE', 'LONGITUDE'], inplace=True)

    # combined below into 'DISCL_SUPPLIER_ABRVNAME' and 'DISCL_SUPPLIER_FULLNAME'


    # Fill DISCL_SUPPLIER_ABRVNAME and DISCL_SUPPLIER_FULLNAME from other supplier columns,
    # then drop the redundant columns.

    # make a copy to be safe if you want to compare before/after
    df = df.copy()

    # Normalize empty strings -> NA on the relevant columns
    supplier_cols = ['SUPPLIER_ABRVNAME', 'SUPPLIER_FULLNAME', 'DISCL_SUPPLIER_ABRVNAME',
                     'DISCL_SUPPLIER_NAME', 'DISCL_SUPPLIER_FULLNAME']
    df[supplier_cols] = df[supplier_cols].replace(r'^\s*$', pd.NA, regex=True)

    # Build DISCL_SUPPLIER_ABRVNAME: choose the first non-null value from preferred sources
    df['DISCL_SUPPLIER_ABRVNAME'] = df[
        ['DISCL_SUPPLIER_ABRVNAME', 'SUPPLIER_ABRVNAME']
    ].bfill(axis=1).iloc[:, 0]

    # Build DISCL_SUPPLIER_FULLNAME: choose the first non-null value from preferred sources
    df['DISCL_SUPPLIER_FULLNAME'] = df[
        ['DISCL_SUPPLIER_FULLNAME', 'SUPPLIER_FULLNAME', 'DISCL_SUPPLIER_NAME']
    ].bfill(axis=1).iloc[:, 0]

    # Optional: tidy whitespace on the new/filled columns
    for c in ['DISCL_SUPPLIER_ABRVNAME', 'DISCL_SUPPLIER_FULLNAME']:
        df[c] = df[c].astype('string').str.strip().replace({'': pd.NA})

    # Drop the now-redundant columns
    df.drop(columns=['SUPPLIER_ABRVNAME', 'SUPPLIER_FULLNAME', 'DISCL_SUPPLIER_NAME'], inplace=True)

    # Quick verification prints (delete or adjust as you like)
    print("Filled DISCL_SUPPLIER_ABRVNAME: non-null count =", df['DISCL_SUPPLIER_ABRVNAME'].notna().sum())
    print("Filled DISCL_SUPPLIER_FULLNAME: non-null count =", df['DISCL_SUPPLIER_FULLNAME'].notna().sum())

    # Example: show rows where a DISCL_ field was filled from another field
    # (run this before/after if you want to compare; here we show current rows where values exist)
    print(df[['DISCL_SUPPLIER_ABRVNAME', 'DISCL_SUPPLIER_FULLNAME']].head(8))

    # combined below into 'DISCL_AREA_NAME' and 'DISTRICT_GEOCODE'

    # Reduce to DISCL_AREA_NAME and DISTRICT_GEOCODE using LOCALITY_NAME and DISTRICT_NAME as fallbacks.

    df = df.copy()

    area_cols = ['DISCL_AREA_NAME', 'LOCALITY_NAME', 'DISTRICT_GEOCODE', 'DISTRICT_NAME']
    # normalise empty strings -> NA
    df[area_cols] = df[area_cols].replace(r'^\s*$', pd.NA, regex=True)

    # Fill DISCL_AREA_NAME: prefer explicit DISCL_AREA_NAME, then DISTRICT_NAME, then LOCALITY_NAME
    df['DISCL_AREA_NAME'] = df[
        ['DISCL_AREA_NAME', 'DISTRICT_NAME', 'LOCALITY_NAME']
    ].bfill(axis=1).iloc[:, 0]

    # Fill DISTRICT_GEOCODE: prefer existing DISTRICT_GEOCODE, then fall back to DISTRICT_NAME
    # (This keeps codes where present; if you prefer to leave codes blank when only names exist, remove 'DISTRICT_NAME' from the list.)
    df['DISTRICT_GEOCODE'] = df[
        ['DISTRICT_GEOCODE']
    ].bfill(axis=1).iloc[:, 0]

    # Trim whitespace and normalise empty strings to NA
    for c in ['DISCL_AREA_NAME', 'DISTRICT_GEOCODE']:
        df[c] = df[c].astype('string').str.strip().replace({'': pd.NA})

    # Drop now-redundant columns
    df.drop(columns=['LOCALITY_NAME', 'DISTRICT_NAME'], inplace=True)

    # Quick checks
    print("Non-null DISCL_AREA_NAME:", df['DISCL_AREA_NAME'].notna().sum())
    print("Non-null DISTRICT_GEOCODE:", df['DISTRICT_GEOCODE'].notna().sum())
    print(df[['DISCL_AREA_NAME', 'DISTRICT_GEOCODE']].head(10))

    # combined below into 'DISCL_SUPPLIER_TYPE'

    # Reduce to DISCL_SUPPLIER_TYPE using TYPE and any whitespace-variant columns as fallbacks.

    df = df.copy()

    # Find relevant original columns:
    orig_type_cols = [c for c in df.columns if c.strip() in {'DISCL_SUPPLIER_TYPE', 'TYPE'}]
    # Example: this will include 'DISCL_SUPPLIER_TYPE', ' DISCL_SUPPLIER_TYPE', and 'TYPE' if present.

    # If none of those columns exist, create the canonical column (all NA) and exit early.
    if not orig_type_cols:
        df['DISCL_SUPPLIER_TYPE'] = pd.NA
        print("No source columns found for supplier type. Created empty 'DISCL_SUPPLIER_TYPE'.")
    else:
        # Normalise empty strings -> NA on those original columns
        df[orig_type_cols] = df[orig_type_cols].replace(r'^\s*$', pd.NA, regex=True)

        # Build an ordered list of fallback columns:
        # prefer exact 'DISCL_SUPPLIER_TYPE' first, then any whitespace variants, then 'TYPE'
        ordered = []
        if 'DISCL_SUPPLIER_TYPE' in df.columns:
            ordered.append('DISCL_SUPPLIER_TYPE')
        # add whitespace variants (names that strip to DISCL_SUPPLIER_TYPE but aren't the exact name)
        ws_variants = [c for c in df.columns if c.strip() == 'DISCL_SUPPLIER_TYPE' and c != 'DISCL_SUPPLIER_TYPE']
        ordered.extend(ws_variants)
        if 'TYPE' in df.columns:
            ordered.append('TYPE')

        # Safeguard: if ordered is empty (shouldn't be), create empty canonical column
        if not ordered:
            df['DISCL_SUPPLIER_TYPE'] = pd.NA
        else:
            # Merge using first non-null value across ordered fallbacks
            df['DISCL_SUPPLIER_TYPE__MERGE'] = df[ordered].bfill(axis=1).iloc[:, 0]

            # Tidy whitespace and normalise empty -> NA
            df['DISCL_SUPPLIER_TYPE__MERGE'] = (
                df['DISCL_SUPPLIER_TYPE__MERGE']
                .astype('string')
                .str.strip()
                .replace({'': pd.NA})
            )

            # Drop the original/raw columns we used (we will keep only canonical name)
            df.drop(columns=[c for c in ordered if c in df.columns], inplace=True)

            # Rename the merge column to canonical name
            df.rename(columns={'DISCL_SUPPLIER_TYPE__MERGE': 'DISCL_SUPPLIER_TYPE'}, inplace=True)

    # Quick checks
    print("Columns now include:", [c for c in df.columns if 'SUPPLIER_TYPE' in c or c == 'TYPE'][:10])
    print("Non-null DISCL_SUPPLIER_TYPE:", df['DISCL_SUPPLIER_TYPE'].notna().sum())
    print(df['DISCL_SUPPLIER_TYPE'].value_counts(dropna=False).head(10))

    df.rename(columns={'CERTIFICATION_NAME':'DISCL_CERTIFICATION_NAME',
     'CERTIFICATION_PCT':'DISCL_CERTIFICATION_PCT',
     'NUMBER_FARMERS':'DISCL_NUMBER_FARMERS',
     'VOLUMES':'DISCL_VOLUMES',
     'VOLUMES_UNIT':'DISCL_VOLUMES_UNIT'}, inplace=True)

    set(df_2023.columns).difference(set(df.columns))

    set(df.columns).difference(set(df_2023.columns))

    # Figure out what to do about NA traders - leave them (that's how df_2023 is)

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step2_columns_aligned.csv", index=False)

    df = pd.read_csv(f'{DATA_DIR}/supplier_map/work/step2_columns_aligned.csv')

    # Copy over the 7 number_farmers and certification values from the '.1' columns to the main columns where missing
    for col in ['DISCL_NUMBER_FARMERS',
           'DISCL_VOLUMES', 'DISCL_VOLUMES_UNIT', 'DISCL_CERTIFICATION_NAME',
           'DISCL_CERTIFICATION_PCT']:
        col_1 = col + '.1'
        mask = df[col].isna() & df[col_1].notna()
        df.loc[mask, col] = df.loc[mask, col_1]         

    df.drop(columns=['DISCL_NUMBER_FARMERS.1',
           'DISCL_VOLUMES.1', 'DISCL_VOLUMES_UNIT.1', 'DISCL_CERTIFICATION_NAME.1',
           'DISCL_CERTIFICATION_PCT.1'], inplace=True)

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step2_columns_aligned.csv", index=False)


def step3_clean_match_and_locate(DATA_DIR):
    """Clean names, match cooperatives to last year's map, assign each to a region, mark traders."""
    import pandas as pd

    df = pd.read_csv(f'{DATA_DIR}/supplier_map/work/step2_columns_aligned.csv')

    # Name-cleaning functions

    import re
    import unicodedata

    import numpy as np

    # Cleaning function
    def move_long_abrvname_to_fullname(row):
        abrv = row['DISCL_SUPPLIER_ABRVNAME']
        fullname = row['DISCL_SUPPLIER_FULLNAME']
        if isinstance(abrv, str) and len(abrv) > 35 and (pd.isna(fullname) or fullname == ""):
            row['DISCL_SUPPLIER_FULLNAME'] = abrv
            row['DISCL_SUPPLIER_ABRVNAME'] = np.nan
        return row

    def clean_abrvname1(col_name):
        """Handle cases where a full name and abbreviated name are given in the abrv name variable."""
        if not isinstance(col_name, str):
            return col_name
        
        patterns = {
            r"UNITE COOPERATIVE AGRICOLE DE DANANE": "COOP UDAN",
            r"COOPERATIVE AGRICOLE BACON ESPOIR": "CABES",
            r"COOPERATIVE AGRICOLE ABOTRE DE NIABLE": "COAANI",
            r"COOPERATIVE AGRICOLE BENKADI": "COOPABENKADI",
            r"COOPERATIVE AGRICOLE D'AGNANFOUTOU": "COESAG",
            r"COOPERATIVE AGRICOLE ZEMESS TAABA DE GBABAM": "COOPAZEG",
            r"COOPERATIVE DES PRODUCTEURS DE YAKASSE ATTOBROU": "COOPROYA",
            r"SOCIETE AGRICOLE BINKADI DE BROUDOUGOU PENDA CA": "SOCABB",
            r"SCOOPAO SOCIETE COOPERATIVE DES AGRICULTEURS DE PETIT OUAGA": "SCOOPAO",
            r"SOCIETE COOPERATIVE SIMPLIFIEE AGRICOLE KAMBONOU DE ARRAH": "SCOAKA",
            r"SOCIETE COOPERATIVE ESPERENCE DE KPELEKRO": "SOCAEK",
            r"SOCIETE COOPERATIVE AVEC CONSEIL D'ADMINISTRATION ENTENTE DE SEGUELA": "COOP CA ES",
            r"COOPERATIVE DES PRODUCTEURS AGRICOLES DE NIABLE": "COOP CA PAN",
            r"COOPERATIVE YEYONIAN DU CANTON ANIASSUE": "COOPYCA",
            r"SOCIETE COOPERATIVE AGRICOLE DE GNATO AVEC CONSEIL D'ADMINISTRATION": "SOCAG",
            r"SOCIETE COOPERATIVE AGRICOLE DE BAYOTA": "SOCABA COOP CA",
            r"SPAD GAGNOA": "SPAD GAGNOA",
            r"SCAT I|SCAT 1": "SCAT 1",
            r"\(CA\)$": " CA ",
            r"\(COOP\)$": " COOP ",
            r"\(SCOOP\)$": " SCOOP "
        }
    
        for pattern, replacement in patterns.items():
            if re.search(pattern, col_name):
                return replacement
        return col_name

    def clean_abrvname2(col_name):
        """Remove common characters used in abbreviated coop names."""
        if not isinstance(col_name, str):
            return col_name
        
        # Normalize string (equivalent to str_trim)
        cleaned_col = col_name.strip()
    
        # Remove specified patterns
        cleaned_col = re.sub(r"\.|[(]|[)]| WAREHOUSE$", "", cleaned_col)
        cleaned_col = re.sub(r"\n|_|/|-", " ", cleaned_col)
        cleaned_col = re.sub(r"Ô", "O", cleaned_col)
    
        # Remove multiple spaces (equivalent to str_squish)
        cleaned_col = " ".join(cleaned_col.split())
    
        return cleaned_col

    def clean_abrvname3(col_name):
        """Remove generic terms like CA, COOP, SCOOP, SCOOPS, and ' - CA'."""
        if not isinstance(col_name, str):
            return col_name

        pattern = r"COOP CA | COOP CA$|COOP | COOP$|SCOOP |SCOOP$|SCOOPS |SCOOPS$|SCOOP|- CA$"
        return re.sub(pattern, "", col_name)

    def clean_fullname(col_name):
        """Clean cooperative full names."""
        if not isinstance(col_name, str):
            return col_name
        
        # Replace various cooperative terms with standardized form
        coop_pattern = r"SOCIETE COOPERATIVE |STE COOP |COPERATIVE |COOPRATIVE |SOCIETE AGRICOLE COOPERATIVE |ENTREPRISE COOPERATIVE |ENTREPRISE AGRICOLE COOPERATIVE |ENTREP COOPERA "
        fn = re.sub(coop_pattern, "COOPERATIVE ", col_name)
    
        # Replace various cafe-cacao terms with standard form
        cafe_pattern = r"DU CAFE&CACAO|DU CAFE & CACAO|DU CAFE& CACAO|DU CAFE &CACAO|DE CAFE&CACAO|DE CAFE & CACAO|DE CAFE& CACAO|DE CAFE &CACAO|DU CAFE-CACAO|DU CAFE - CACAO|DU CAFE- CACAO|DU CAFE -CACAO|DE CAFE-CACAO|DE CAFE - CACAO|DE CAFE- CACAO|DE CAFE- CACAO|CAFE&CACAO|CAFE & CACAO|CAFE& CACAO|CAFE &CACAO|CAFE-CACAO|CAFE - CACAO|CAFE- CACAO|CAFE -CACAO|DU CAFE ET DU CACAO|DE CAFE ET DE CACAO|CAFE ET DU CACAO|CAFE ET DE CACAO|DU CAFE ET CACAO|DE CAFE ET CACAO|CAFE ET CACAO|DU CAFE CACAO|DE CAFE CACAO|CAFE CACAO|CAFECACAO|DU CAFE COCOA"
        fn = re.sub(cafe_pattern, "STD_CAFE_CACAO_STD", fn)
    
        # Replace back with readable form
        return re.sub("STD_CAFE_CACAO_STD", "CAFE ET CACAO", fn)

    def clean_fullname_manual(col_name):
        """Apply manual corrections to specific cooperative names."""
        if not isinstance(col_name, str):
            return col_name
        
        if re.search(r"COOPERATIVE AGRICOLE SOLIDARITE DE BLOLEQUIN", col_name):
            return "ENTREPRISE COOPERATIVE AGRICOLE DE BLOLEQUIN"
        elif re.search(r"COOPERATIVE POUR L'AMELIORAT DU REVENU DU PLANTEUR DE CI", col_name):
            return "COOPERATIVE POUR L'AMELIORATION DU REVENU DU PLANTEUR"
        elif re.search(r"COOPERATIVE SABABOUGNOUMAN DAGADJI", col_name):
            return "COOPERATIVE SABABOUGNOUMAN DE DAGADJI"
        elif re.search(r"ROBERT", col_name) and re.search(r"PORTE", col_name):
            return "ENTREPRISE COOPERATIVE AGRICOLE DES PRODUCTEURS CAFE ET CACAO DE ROBERT-PORTE"
        elif re.search(r"MAN EDI ANOUANZE", col_name):
            return "SOCIETE COOPERATIVE AGRICOLE MAN EDI ANOUANZE"
        return col_name

    df = df.apply(move_long_abrvname_to_fullname, axis=1)

    # Apply cleaning functions to the abbreviated supplier name column
    df['DISCL_SUPPLIER_ABRVNAME_CLEANED'] = df['DISCL_SUPPLIER_ABRVNAME'].apply(clean_abrvname1)
    df['DISCL_SUPPLIER_ABRVNAME_CLEANED'] = df['DISCL_SUPPLIER_ABRVNAME_CLEANED'].apply(clean_abrvname2)
    df['DISCL_SUPPLIER_ABRVNAME_CLEANED'] = df['DISCL_SUPPLIER_ABRVNAME_CLEANED'].apply(clean_abrvname3)

    # Apply full name cleaning functions to the full supplier name column
    df['DISCL_SUPPLIER_FULLNAME_CLEANED'] = df['DISCL_SUPPLIER_FULLNAME'].apply(clean_fullname)
    df['DISCL_SUPPLIER_FULLNAME_CLEANED'] = df['DISCL_SUPPLIER_FULLNAME_CLEANED'].apply(clean_fullname_manual)

    def set_supplier_type_cooperative(row):
        if isinstance(row['DISCL_SUPPLIER_FULLNAME_CLEANED'], str) and "COOPERATIVE " in row['DISCL_SUPPLIER_FULLNAME_CLEANED']:
            row['DISCL_SUPPLIER_TYPE'] = "COOPERATIVE"
        return row

    df = df.apply(set_supplier_type_cooperative, axis=1)

    df_2023 = pd.read_csv(f'{DATA_DIR}/supplier_map/last_year/cooperatives_2023.csv', sep=';')

    from fuzzywuzzy import fuzz, process
    import numpy as np
    import re

    # List of common words/phrases to ignore
    ignore_phrases = [
        "SOCIETE", "COOPERATIVE", "COOPÉRATIVE", "AVEC", "CONSEIL D'ADMINISTRATION", "AGRICOLE", 
        "DES","PRODUCTEURS", "COOP", "WAREHOUSE", "SAND BOX", "-CA", "COOPÉRATIVE", "SOCIÉTÉ",
        "CONSEILD'ADMINISTRATION","AGRICULTEURS", "ET", "DE"
    ]

    def remove_ignore_phrases(text, ignore_phrases):
        if not isinstance(text, str):
            return text
        for phrase in ignore_phrases:
            text = re.sub(re.escape(phrase), '', text, flags=re.IGNORECASE)
        return ' '.join(text.split())

    # Step 1: Clean names for fuzzy matching
    abrv_2023 = df_2023['DISCL_SUPPLIER_ABRVNAME'].dropna().unique().tolist()
    full_2023 = df_2023['DISCL_SUPPLIER_FULLNAME'].dropna().unique().tolist()
    abrv_2024 = df['DISCL_SUPPLIER_ABRVNAME_CLEANED'].dropna().unique().tolist()
    full_2024 = df['DISCL_SUPPLIER_FULLNAME_CLEANED'].dropna().unique().tolist()

    abrv_2023_clean = [remove_ignore_phrases(x, ignore_phrases) for x in abrv_2023]
    abrv_2024_clean = [remove_ignore_phrases(x, ignore_phrases) for x in abrv_2024]
    full_2023_clean = [remove_ignore_phrases(x, ignore_phrases) for x in full_2023]
    full_2024_clean = [remove_ignore_phrases(x, ignore_phrases) for x in full_2024]

    # Step 2: Build fuzzy match mapping for abrv and full names
    fuzzy_match_map_abrv = {}
    for orig_val, val in zip(abrv_2024_clean, abrv_2024_clean):
        match, score = process.extractOne(val, abrv_2023_clean, scorer=fuzz.token_sort_ratio)
        if score >= 90 and match is not None:
            matched_idx = abrv_2023_clean.index(match)
            matched_original = abrv_2023[matched_idx]
            print(f"Matching {orig_val} to {matched_original} with score {score}")
            fuzzy_match_map_abrv[orig_val] = matched_original

    fuzzy_match_map_full = {}
    for orig_val, val in zip(full_2024_clean, full_2024_clean):
        match, score = process.extractOne(val, full_2023_clean, scorer=fuzz.token_sort_ratio)
        if score >= 90 and match is not None:
            matched_idx = full_2023_clean.index(match)
            matched_original = full_2023[matched_idx]
            print(f"Matching {orig_val} to {matched_original} with score {score}")
            fuzzy_match_map_full[orig_val] = matched_original

    # Step 3: Create lookup from abrv/full names to row in df_2023
    df_2023_lookup_abrv = {row['DISCL_SUPPLIER_ABRVNAME']: row for idx, row in df_2023.iterrows() if isinstance(row['DISCL_SUPPLIER_ABRVNAME'], str)}
    df_2023_lookup_full = {row['DISCL_SUPPLIER_FULLNAME']: row for idx, row in df_2023.iterrows() if isinstance(row['DISCL_SUPPLIER_FULLNAME'], str)}

    # Step 4: Impute using fuzzy match and update matched value
    cols_to_copy = [
        'DISCL_LONGITUDE', 'DISCL_LATITUDE', 'DISTRICT_NAME', 'DISTRICT_GEOCODE',
        'LOCALITY_NAME', 'DISCL_AREA_NAME'
    ]

    def impute_row_fuzzy(row):
        abrv_clean = row.get('DISCL_SUPPLIER_ABRVNAME_CLEANED')
        full_clean = row.get('DISCL_SUPPLIER_FULLNAME_CLEANED')
        match_row = None
        matched_abrv = None
        matched_full = None

        # If not found, try abrv name match
        if match_row is None and isinstance(full_clean, str) and full_clean in fuzzy_match_map_full:
            matched_full = fuzzy_match_map_full[full_clean]
            match_row = df_2023_lookup_full.get(matched_full)
            row['DISCL_SUPPLIER_FULLNAME_CLEANED'] = matched_full

        if isinstance(abrv_clean, str) and abrv_clean in fuzzy_match_map_abrv:
            matched_abrv = fuzzy_match_map_abrv[abrv_clean]
            match_row = df_2023_lookup_abrv.get(matched_abrv)
            row['DISCL_SUPPLIER_ABRVNAME_CLEANED'] = matched_abrv

        if match_row is not None:
            for col in cols_to_copy:
                if col in row and (pd.isna(row[col]) or row[col] == ""):
                    row[col] = match_row.get(col, np.nan)
        return row

    df = df.apply(impute_row_fuzzy, axis=1)

    df.to_csv(f'{DATA_DIR}/supplier_map/work/step3_names_cleaned_and_matched.csv', index=False)

    # Fill missing geocodes and check use of company vs. trader

    df = pd.read_csv(f'{DATA_DIR}/supplier_map/work/step3_names_cleaned_and_matched.csv')
    df_2023 = pd.read_csv(f'{DATA_DIR}/supplier_map/last_year/cooperatives_2023.csv', sep=';')

    import geopandas as gpd
    df = pd.read_csv(f'{DATA_DIR}/supplier_map/work/step3_names_cleaned_and_matched.csv')
    df_2023 = pd.read_csv(f'{DATA_DIR}/supplier_map/last_year/cooperatives_2023.csv', sep=';')

    print(df_2023.head())
    print(df.head())

    print(df.describe())
    print(df_2023.describe())

    print(df.DISCL_AREA_NAME.unique())
    print(df.DISTRICT_GEOCODE.unique())

    # Load the file
    fp = f"{DATA_DIR}/regions/departments.geojson"
    gdf = gpd.read_file(fp)

    # View the first few rows
    print(gdf.head())

    from shapely.geometry import Point

    # 1. Define the point (Longitude, Latitude)
    # User provided: 6.9256... (Lat), -6.0637... (Lon)
    lat = 6.768233137521048
    lon = -6.859370618032626
    point = Point(lon, lat)

    # 2. Check which polygon contains the point
    # 'geometry' is the column with the POLYGON data
    mask = gdf['geometry'].contains(point)

    # 3. Filter the dataframe to get the matching row
    matching_row = gdf[mask]

    # 4. Print the result
    if not matching_row.empty:
        print(f"The point is in: {matching_row.iloc[0]['LVL_4_NAME']}")
        # Optional: Print the clean name
        # print(f"Clean Name: {matching_row.iloc[0]['LVL_4_NAME_CLEAN']}")
    else:
        print("Point is not inside any region in the GeoDataFrame.")

    # # Impute DISTRICT_GEOCODES

    import pandas as pd
    import geopandas as gpd
    import unicodedata
    import numpy as np

    # ==========================================
    # 0. SETUP & LOAD DATA
    # ==========================================
    # File Paths
    PATH_MAIN = f'{DATA_DIR}/supplier_map/work/step3_names_cleaned_and_matched.csv'
    PATH_2023 = f'{DATA_DIR}/supplier_map/last_year/cooperatives_2023.csv'
    PATH_GEO = f"{DATA_DIR}/regions/departments.geojson"

    # Load Data
    print("Loading datasets...")
    df = pd.read_csv(PATH_MAIN)
    df_2023 = pd.read_csv(PATH_2023, sep=';')
    gdf = gpd.read_file(PATH_GEO)

    # Fills NaNs in 'CLEANED' with value from 'TRADER_NAME'
    df['DISCL_SUPPLIER_ABRVNAME_CLEANED'] = df['DISCL_SUPPLIER_ABRVNAME_CLEANED'].fillna(df['DISCL_TRADER_NAME'])

    # 1. Ensure empty strings are treated as NaN so fillna works
    cols_to_fix = ['DISCL_SUPPLIER_ABRVNAME_CLEANED', 'DISCL_SUPPLIER_ABRVNAME', 'DISCL_SUPPLIER_FULLNAME']
    df[cols_to_fix] = df[cols_to_fix].replace(r'^\s*$', np.nan, regex=True)

    # 2. Impute: 
    #    Priority 1: Keep existing CLEANED
    #    Priority 2: Fill with ABRV
    #    Priority 3: Fill with FULLNAME
    df['DISCL_SUPPLIER_ABRVNAME_CLEANED'] = df['DISCL_SUPPLIER_ABRVNAME_CLEANED']\
        .fillna(df['DISCL_SUPPLIER_ABRVNAME'])\
        .fillna(df['DISCL_SUPPLIER_FULLNAME_CLEANED'])\
        .fillna(df['DISCL_SUPPLIER_FULLNAME'])

    # Check results
    print("Missing cleaned names after imputing:", df['DISCL_SUPPLIER_ABRVNAME_CLEANED'].isna().sum())

    # ==========================================
    # 1. HELPER FUNCTIONS & TEXT CLEANING
    # ==========================================

    def clean_text(text):
        """Standardizes text: removes accents, upper case, strips whitespace."""
        if pd.isna(text) or text == "" or str(text).lower() == 'nan':
            return None
        text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'ignore').decode('utf-8')
        return text.upper().strip()

    def aggressive_clean(text):
        """Strips 'SAND BOX', 'COOP CA' and other noise to find the core name."""
        if pd.isna(text):
            return None
        text = str(text).upper().strip()
        noise_list = [
            'SAND BOX', 'SANS BOX', 'SAND_BOX', 'SANDBOX', 
            ' IN PROD', ' TEST', ' COOP CA', ' COOP-CA', ' SCOOPS'
        ]
        for noise in noise_list:
            text = text.replace(noise, '')
        return text.strip()

    print("Initial text cleaning...")
    # Clean Reference Data
    gdf['LVL_4_NAME_CLEAN'] = gdf['LVL_4_NAME'].apply(clean_text)
    df_2023['DISTRICT_NAME_CLEAN'] = df_2023['DISTRICT_NAME'].apply(clean_text)

    # Clean Main Data Area
    df['DISCL_AREA_NAME'] = df['DISCL_AREA_NAME'].apply(clean_text) # Standardize basic input

    # Create an aggressive clean column for matching logic (does not overwrite original yet)
    df['CLEANED_RESIDUAL_NAME'] = df['DISCL_SUPPLIER_ABRVNAME'].apply(aggressive_clean)


    # ==========================================
    # 2. DEFINE MAPPINGS
    # ==========================================
    print("Building dictionaries...")

    # GeoJSON Reference Maps
    name_to_geocode_gdf = dict(zip(gdf['LVL_4_NAME_CLEAN'], gdf['LVL_4_CODE']))
    geocode_to_name_gdf = dict(zip(gdf['LVL_4_CODE'], gdf['LVL_4_NAME_CLEAN']))

    # 2023 Reference Data Maps
    ref_coops = df_2023.dropna(subset=['SUPPLIER_ABRVNAME']).drop_duplicates('SUPPLIER_ABRVNAME')
    coop_to_name_2023 = dict(zip(ref_coops['SUPPLIER_ABRVNAME'], ref_coops['DISTRICT_NAME_CLEAN']))
    coop_to_code_2023 = dict(zip(ref_coops['SUPPLIER_ABRVNAME'], ref_coops['DISTRICT_GEOCODE']))

    # --- DICTIONARY A: Manual Fixes (Typos, Foreign, Misplaced) ---
    manual_fix_map = {
        # Typos & Sub-locations
        'BAKAYO': 'SASSANDRA', "N'DOUCI": 'TIASSALE', 'BINHOUYE': 'ZOUAN-HOUNIEN',
        'KPOUEBO (TOUMODI)': 'TOUMODI', 'HERMANKONO DIES (GUITRY)': 'GUITRY', 'BONON': 'BOUAFLE',
        'BAYOTA (GAGNOA)': 'GAGNOA', 'MENE CENTRE (SAN-PEDRO)': 'SAN-PEDRO', 'DAGADJI': 'SAN-PEDRO',
        'ABONGOUA': 'ARRAH', 'SAN PEDRO': 'SAN-PEDRO', 'GNATO': 'TABOU', 'BIANKOUMAN': 'BIANKOUMA',
        'GOUDI': 'GAGNOA', 'MENEE CENTRE/GABIADJI': 'SAN-PEDRO', 'GRAND-BEREBY': 'TABOU',
        'TINHOU': 'BLOLEQUIN', 'YAKASSE ATTOBROU': 'YAKASSE-ATTOBROU', 'AFFERY': 'AKOUPE',
        'GUIBEROUA': 'GAGNOA', 'GRAND LAHOU': 'GRAND-LAHOU', 'GRABO': 'TABOU',
        'DIEGONEFLA': 'OUME', 'SEGUELLA': 'SEGUELA', 'TOULEPLEU': 'TOULEUPLEU',
        'GRAND-ZATTRY': 'SOUBRE', 'DIBY': 'SAKASSOU',

        # Coop Names masquerading as Locations
        'ECAKOOG': 'LAKOTA', 'SCOOPAKAM': 'DIVO', 'SCOOWEND COOP-CA': 'SAN-PEDRO',
        'CASIB COOP-CA': 'BLOLEQUIN', 'COOP-CA ADA': 'SAN-PEDRO', 'BARA COOP-CA': 'BANGOLO',
        'AGRIAL COOP-CA': 'DALOA', 'COPAWEB COOP-CA': 'SOUBRE', 'ECAPA GZ COOP-CA': 'SOUBRE',
        'SOCAAN COOP-CA': 'ADZOPE',

        # Foreign / Garbage -> Map to None to drop later
        'SUHUM MUNICIPAL': None, 'MBANGASSINA': None, 'NTUI': None,
        'LOCATION': None, 'AVERAGE PER FARMER': None,
    
        # Reset Broad Areas to empty string for re-mapping
        'CENTRE-EST': '', 'EST': '', 'SUD-EST': '', 'OUEST': '',
        'CENTRE-OUEST': '', 'SUD-OUEST': '', 'NORD': '', 'SUD': '', 'CENTRE': ''
    }

    # --- DICTIONARY B: Broad Regions to Specifics (via Coop Name) ---
    dict_broad_names = {
        # Est / Abengourou
        'CAAA': 'ABENGOUROU', 'CAABRO': 'ABENGOUROU', 'CAAN': 'ABENGOUROU', 
        'CAMAP': 'AGNIBILEKRO', 'CAPA': 'ABENGOUROU', 'CAPRESSA': 'ABENGOUROU', 
        'CEAA COOP CA': 'ABENGOUROU', 'COAKA': 'ABENGOUROU', 'COOAAB-COOP CA': 'ABENGOUROU', 
        'COOP CA ABOTRE': 'ABENGOUROU', 'COOP CA ESPOIR': 'ABENGOUROU', 'COOP CA NOBIELTO': 'ABENGOUROU', 
        'COOPAYAF': 'ABENGOUROU', 'COOPAZA': 'ABENGOUROU', 'COOPRAZO': 'ABENGOUROU', 
        'COOPYCA': 'ABENGOUROU', 'CP2A': 'ABENGOUROU', 'SCAANIAS': 'ABENGOUROU', 
        'SCOAPANI': 'ABENGOUROU', 'SOLIDARITE': 'ABENGOUROU',
        # Ouest / Man
        'CABA': 'MAN', 'CADB': 'BIANKOUMA', 'CADT': 'MAN', 'CAMOBIAN': 'BIANKOUMA', 
        'CAPB': 'MAN', 'CAPROD': 'MAN', 'COOP CA SPAM MAN': 'MAN', 'COOP CA WEND SONGDA': 'DANANE', 
        'COOP-CA-UDAN': 'DANANE', 'COOP-CA-PAN': 'DANANE', 'COOPAHK': 'MAN', 'COOPANAM': 'MAN', 
        'LAFI BEBE DE MAN': 'MAN', 'NWK': 'MAN', 'SCAB': 'SIPILOU', 'SCAG COOP CA': 'MAN', 
        'SCAPCC': 'MAN', 'SCAW COOP-CA': 'MAN', 'SCOOP CAYEM': 'MAN', 'SCOOPS JST': 'MAN', 
        'SCOOPS LA PAIX': 'MAN', 'SCOOPS SCAG': 'MAN', 'SCOOPS-AH': 'MAN', 'SCOOPS-APRAB': 'MAN', 
        'SINIKAN-SCOOPAS': 'MAN', 'SOCAET COOP CA': 'MAN',
        # Centre-Ouest
        'CABG SCOOPS': 'DALOA', 'CAEG': 'DALOA', 'CAKB': 'DALOA', 'CEDA': 'DALOA', 
        'COAM': 'VAVOUA', 'COOBADI': 'DALOA', 'COOP-CA-CABS': 'DALOA', 'COOPADEF': 'DALOA', 
        'COOPAGARO': 'DALOA', 'COOPAGES': 'DALOA', 'COOPAGO': 'DALOA', 'COOPAKCODI': 'DALOA', 
        'COOPAMDI': 'DALOA', 'COOPATESA': 'DALOA', 'COOPINA': 'DALOA', 'CPACD': 'DALOA', 
        'CPI': 'ZUENOULA', 'ECODEBO': 'DALOA', 'ECOPADI': 'DALOA', 'FLRI COOPADIM': 'DALOA', 
        'IQJ': 'VAVOUA', 'LE PROGRES': 'GAGNOA', 'S-COOP COOPRADA': 'VAVOUA', 'SC WLSA COOP CA': 'DALOA', 
        'SCAAO': 'DALOA', 'SCABK': 'DALOA', 'SCABODI': 'DALOA', 'SCAC': 'DALOA', 'SCAGB': 'DALOA', 
        'SCAGG': 'DALOA', 'SCAM': 'DALOA', 'SCANG': 'DALOA', 'SCAPEKO': 'DALOA', 'SCARDI': 'DALOA', 
        'SCBPAG': 'DALOA', 'SCELA COOP-CA': 'DALOA', 'SCOOPA': 'DALOA', 'SCOOPAAS': 'DALOA', 
        'SCOOPAKAM': 'DALOA', 'SCOOPAKOKO': 'DALOA', 'SCOOPECO': 'DALOA', 'SCOOPNIA SCOOPS': 'DALOA', 
        'SCOOPS AGRI.BIO': 'DALOA', 'SCOOPS-CODEMA': 'DALOA', 'SCOOPS-LTDV': 'DALOA', 'SCOOPS-UPRAD': 'GAGNOA', 
        'SOCABB': 'DALOA', 'SOCAGS': 'DALOA', 'SOCAHI': 'DALOA', 'SOCOOPELA': 'DALOA', 'SOCOPADOU': 'DALOA', 
        'SOCOPAL SCOOPS': 'DALOA', 'SOCOPDAL SCOOPS': 'DALOA', 'CAFUVA': 'VAVOUA', 'COOP CA CAPLI': 'ZUENOULA',
        # Sud-Ouest
        'CABGB': 'SAN-PEDRO', 'CABID': 'SOUBRE', 'CABING': 'SOUBRE', 'CAC': 'SOUBRE', 
        'CADA': 'SASSANDRA', 'CADEDO': 'SOUBRE', 'CAL2B': 'SOUBRE', 'CAPL': 'SOUBRE', 
        'CAPO': 'SOUBRE', 'CATBK': 'SOUBRE', 'CJPK': 'SOUBRE', 'COOP CA ANZUE II': 'SOUBRE', 
        'COOP CA BIRBA': 'SAN-PEDRO', 'COOP CA COANI': 'SOUBRE', 'COOP CA COOPAA': 'SOUBRE', 
        'COOP JCAS': 'SOUBRE', 'COOP-CA CAGNAN': 'SOUBRE', 'COOP-CA COANGNA': 'SOUBRE', 
        'COOP-CA COOPABIN': 'SOUBRE', 'COOP-CA COOPADO': 'SOUBRE', 'COOP-CA NECAB': 'SOUBRE', 
        'COOP-CA-ABO': 'SOUBRE', 'COOPALBA': 'SOUBRE', 'COOPAOU': 'SOUBRE', 'COOPASM': 'SOUBRE', 
        'COOPAZEG': 'SOUBRE', 'CPSL': 'SOUBRE', 'ECAB': 'SOUBRE', 'ECAMOG': 'SOUBRE', 
        'ECEAGN COOP-CA': 'TABOU', 'ECOPAS': 'SOUBRE', 'ECSP': 'SAN-PEDRO', 'ECSP PURATOS': 'SAN-PEDRO', 
        'FLRI SOCAMA': 'SOUBRE', 'SCAACI': 'SOUBRE', 'SCAEG': 'SOUBRE', 'SCAEPGY': 'SOUBRE', 
        'SCAND': 'SOUBRE', 'SCAPD': 'SOUBRE', 'SCAPUD': 'SOUBRE', 'SCAS COOP-CA': 'SOUBRE', 
        'SCASOU': 'SOUBRE', 'SCO SACI': 'SOUBRE', 'SCOOP CAES': 'BONDOUKOU', 'SCOOPA CA': 'SAN-PEDRO', 
        'SCOOPAC': 'SOUBRE', 'SCOOPADJI': 'SOUBRE', 'SCOOPS AL': 'SOUBRE', 'SCOOPS COOP.A.SAM': 'SOUBRE', 
        'SCOOPS COOPAA': 'SOUBRE', 'SCOOPS SCAT 1': 'MEAGUI', 'SCOOPS SCSAG': 'TABOU', 
        'SCOOPS SNCC': 'SOUBRE', 'SCOOPS WEBE': 'SOUBRE', 'SCOOWEND': 'SOUBRE', 'SCSPA': 'SOUBRE', 
        'SCUW': 'SOUBRE', 'SO.CO.SA.DA': 'SOUBRE', 'SO.COA.MO': 'SOUBRE', 'SOCADJO': 'SOUBRE', 
        'SOCAG': 'SOUBRE', 'SOCAGNIPI': 'SOUBRE', 'SOCAGRI2': 'SOUBRE', 'SOCAJ': 'SOUBRE', 
        'SOCOPADOGBO': 'SOUBRE', 'SOCOPEK': 'SOUBRE', 'SOCOSOM': 'SOUBRE', 'UPAS': 'SOUBRE', 'CADESA': 'SOUBRE',
        # Others
        'CANK': 'DUEKOUE', 'CASODU': 'DUEKOUE', 'COOP CA KWS': 'DUEKOUE', 'COOP CA GCT': 'DUEKOUE', 
        'COOP TEEGA WENDE': 'DUEKOUE', 'SCOOPASG': 'DUEKOUE', 'SCOOPS AKY': 'DUEKOUE', 
        'SCOOPS BADEMAYA': 'DUEKOUE', 'SCOOPS EPG': 'DUEKOUE', 'SC2WK COOP CA': 'DUEKOUE', 
        'COOP-CA INCHALA': 'DUEKOUE', 'CABES': 'ABOISSO', 'CNAD': 'ABOISSO', 'COABIA': 'ADIAKE', 
        'COESAG': 'ABOISSO', 'COOPRAS': 'ABOISSO', 'COOPROYA': 'ABOISSO', 'ECAAF': 'ABOISSO', 
        'SCAK': 'ADZOPE', 'SCOOPS 3A': 'ABOISSO', 'SOCAEK': 'ABOISSO', 'SO.CC.NA': 'ABOISSO',
        'CABOHGA COOP CA': 'LAKOTA', 'CIPACCA': 'GAGNOA', 'CODERLACS': 'YAMOUSSOUKRO', 
        'COOP CA COPACOL': 'LAKOTA', 'COOPRADI': 'LAKOTA', 'ECAESB': 'TOUMODI', 'ECOOPAK': 'DIVO', 
        'SCOAWWASI': 'DIVO', 'SCOOPS ABOKA': 'DIVO', 'SCOOPS BAD': 'AGBOVILLE', 'SCOOPS YAT': 'TIASSALE', 
        'SOCABA': 'AGBOVILLE', 'SOCABA SCOOPS': 'AGBOVILLE', 'COOP CAES': 'BONDOUKOU', 
        'COOPABENKADI': 'BONDOUKOU', 'FLRI NANTEBESSOU': 'BONDOUKOU', 'CARET': 'DAOUKRO', 'SCAESG': 'BONGOUANOU',
    }

    # --- DICTIONARY C: Residuals / Sand Box / Embedded Locations ---
    residual_fix_map = {
        'BMC VAVOUA': 'VAVOUA', 'SPAD GAGNOA': 'GAGNOA', 'ECO LAKOTA': 'LAKOTA',
        'SPAD GUIGLO': 'GUIGLO', 'BARRA GABIADJI': 'SAN-PEDRO', 'SCOOPS SCOEL BONGOUANOU': 'BONGOUANOU',
        'ESPOIR VAVOUA': 'VAVOUA', 'SCAW MAN': 'MAN', 'APM GAGNOA': 'GAGNOA',
        'COOPABE BOKASSO': 'BOUAFLE', 'CABID II': 'SOUBRE', 'SCAP-CC': 'MAN',
        'ECEPAG': 'GAGNOA', 'SOCBPI': 'BEOUMI', 'SOCAET2': 'MAN', 'CALTDV': 'DALOA',
        # Ghana / Foreign / Garbage
        'ASETENAPA': None, 'ASUNAFO': None, 'KUKUOM': None, 'DAKUA': None, 'ABOCFA': None,
        'ASANKRAGWA': None, 'TARKWA HUNI': None, 'ASSIN': None, 'ESCOPAG': None,
        'CDI FG': None, 'FARMER GROUP': None, 'FG': None, 'AAT': None, 'IIAP': None, 'HKF 7': None
    }

    # --- DICTIONARY D: Final Patch (Stubborn Coops) ---
    final_patch_map = {
        'SCANDI WAREHOUSE': 'SOUBRE', 'SCAND-COOP CA': 'SOUBRE', 'COOP CA SCAND': 'SOUBRE',
        'SOCOAMO': 'SOUBRE', 'COOPALBA COOP-CA': 'SOUBRE', 'SOCONEL-SCOOPS': 'SOUBRE',
        'COOP CATBK': 'SOUBRE', 'SCAEPGY': 'SOUBRE', 'CABING': 'SOUBRE', 'SCSPA': 'SOUBRE',
        'SCOOPS COOP.A.SAM': 'SOUBRE', 'SCOOPNAS': 'SOUBRE', 'COOBADI': 'DALOA',
        'COOBADI COOP-CA': 'DALOA', 'COOPINA COOP-CA': 'DALOA', 'SCOOPS-AGRIOBIO': 'DALOA',
        'SOCAHI': 'DALOA', 'SOCOPADOU': 'DALOA', 'CAREBO': 'DALOA', 'CAPEDIG (PART OF ECOOKIM)': 'DALOA',
        'UCA': 'DALOA', 'ECAKOOG': 'LAKOTA', 'SCOOP ABOKA': 'DIVO', 'IQJ': 'VAVOUA',
        'SCOOPAVI': 'VAVOUA', 'COOPAGG': 'GUEYO', 'ECAPR': 'SINFRA', 'COOP-CA-ECAPR': 'SINFRA',
        'SOCAET2': 'MAN', 'BECIDA': 'ADZOPE', 'COOKADI': 'KANI', 'COOPAEEN COOP-CA': 'ABENGOUROU',
        'SCOOPRAZA COOP-CA': 'ABENGOUROU', 'CAEZ-COOP-CA': 'ABENGOUROU', 'COOP CA ABO': 'ABOISSO',
        'COOPRAMA-CA': 'ABOISSO', 'SCAND': 'SOUBRE', 'CAAA': 'ABENGOUROU', 'SOCOAMO COOP-CA': 'SOUBRE',
        'COOPAEEN': 'ABENGOUROU', 'COOPALBA': 'SOUBRE', 'SOCONPAYAT COOP-CA': 'YAKASSE-ATTOBROU',
        'SCAA CI': 'ABENGOUROU', 'COOPASM': 'SOUBRE', 'COOPRAS': 'ABOISSO'
    }

    # ==========================================
    # 3. EXECUTION: APPLY LOGIC
    # ==========================================

    # 1. Move Misplaced Names
    # (Rows where the Area Name is actually a Coop Name)
    misplaced_coops = [k for k in manual_fix_map.keys() if k in df['DISCL_AREA_NAME'].unique()]
    mask_misplaced = df['DISCL_AREA_NAME'].isin(misplaced_coops)
    # Copy the area value to supplier abbreviation before we overwrite the area
    df.loc[mask_misplaced, 'DISCL_SUPPLIER_ABRVNAME'] = df.loc[mask_misplaced, 'DISCL_AREA_NAME']

    # 2. Apply Manual Fix Map
    # (Fixes typos, sets broad regions to "", maps foreign to None)
    print("Applying manual fixes...")
    df['DISCL_AREA_NAME'] = df['DISCL_AREA_NAME'].replace(manual_fix_map)

    # 3. Map Broad/Empty Areas using Aggressive Cleaned Name
    # (This matches 'CAAA SAND BOX' to 'ABENGOUROU' via 'CAAA')
    print("Mapping broad/missing areas via coop name...")
    mask_missing = (df['DISCL_AREA_NAME'] == '') | (df['DISCL_AREA_NAME'].isna())
    df.loc[mask_missing, 'DISCL_AREA_NAME'] = df.loc[mask_missing, 'CLEANED_RESIDUAL_NAME'].map(dict_broad_names)

    # 4. Map Residuals (Sandboxes and Hidden Locations)
    mask_missing = (df['DISCL_AREA_NAME'] == '') | (df['DISCL_AREA_NAME'].isna())
    df.loc[mask_missing, 'DISCL_AREA_NAME'] = df.loc[mask_missing, 'CLEANED_RESIDUAL_NAME'].map(residual_fix_map)

    # 5. Apply Final Patch (Stubborn Coops)
    mask_missing = (df['DISCL_AREA_NAME'] == '') | (df['DISCL_AREA_NAME'].isna())
    # Try mapping against the original ABRV for these specific leftovers
    df.loc[mask_missing, 'DISCL_AREA_NAME'] = df.loc[mask_missing, 'DISCL_SUPPLIER_ABRVNAME'].map(final_patch_map)

    # ==========================================
    # 4. GEOCODING & SPATIAL JOIN
    # ==========================================
    print("Standardizing geography...")

    # 1. Clean Area Name to match GeoJSON keys
    df['DISCL_AREA_NAME_CLEAN'] = df['DISCL_AREA_NAME'].apply(clean_text)

    # 2. Lookup GeoCodes
    df['DISTRICT_GEOCODE'] = df['DISCL_AREA_NAME_CLEAN'].map(name_to_geocode_gdf)

    # 3. Fallback: 2023 Reference Data
    mask_no_code = df['DISTRICT_GEOCODE'].isna()
    df.loc[mask_no_code, 'DISTRICT_GEOCODE'] = df.loc[mask_no_code, 'DISCL_SUPPLIER_ABRVNAME'].map(coop_to_code_2023)
    df.loc[mask_no_code, 'DISCL_AREA_NAME_CLEAN'] = df.loc[mask_no_code, 'DISCL_SUPPLIER_ABRVNAME'].map(coop_to_name_2023)

    # 4. Fallback: Spatial Join (Lat/Lon)
    mask_needs_spatial = df['DISTRICT_GEOCODE'].isna() & df['DISCL_LATITUDE'].notna() & df['DISCL_LONGITUDE'].notna()

    if mask_needs_spatial.sum() > 0:
        print(f"Running spatial join for {mask_needs_spatial.sum()} rows...")
        temp_gdf = gpd.GeoDataFrame(
            df.loc[mask_needs_spatial],
            geometry=gpd.points_from_xy(df.loc[mask_needs_spatial, 'DISCL_LONGITUDE'], 
                                        df.loc[mask_needs_spatial, 'DISCL_LATITUDE']),
            crs="EPSG:4326"
        )
    
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
        
        joined = gpd.sjoin(temp_gdf, gdf[['LVL_4_CODE', 'LVL_4_NAME_CLEAN', 'geometry']], how='left', predicate='within')
        joined = joined[~joined.index.duplicated(keep='first')]
    
        df.loc[joined.index, 'DISTRICT_GEOCODE'] = df.loc[joined.index, 'DISTRICT_GEOCODE'].fillna(joined['LVL_4_CODE'])
        df.loc[joined.index, 'DISCL_AREA_NAME_CLEAN'] = df.loc[joined.index, 'DISCL_AREA_NAME_CLEAN'].fillna(joined['LVL_4_NAME_CLEAN'])

    # ==========================================
    # 5. FINAL CLEANUP & DROP
    # ==========================================

    # Sync Name and Code one last time
    df['DISCL_AREA_NAME_CLEAN'] = df['DISCL_AREA_NAME_CLEAN'].fillna(df['DISTRICT_GEOCODE'].map(geocode_to_name_gdf))
    df['DISTRICT_GEOCODE'] = df['DISTRICT_GEOCODE'].fillna(df['DISCL_AREA_NAME_CLEAN'].map(name_to_geocode_gdf))

    # Set the final Area Name column
    df['DISCL_AREA_NAME'] = df['DISCL_AREA_NAME_CLEAN']

    # FINAL DROP
    # Only drop rows if we have failed to find a location AND the explicit mapping identified them as None/Garbage
    initial_len = len(df)
    df = df.dropna(subset=['DISCL_AREA_NAME', 'DISTRICT_GEOCODE'], how='all')

    print("--- Final Status ---")
    print(f"Total Rows: {len(df)} (Dropped {initial_len - len(df)} rows)")
    print("Missing DISCL_AREA_NAME:", df['DISCL_AREA_NAME'].isna().sum())
    print("Missing DISTRICT_GEOCODE:", df['DISTRICT_GEOCODE'].isna().sum())

    if df['DISTRICT_GEOCODE'].isna().sum() > 0:
        print("\nStill missing codes for:")
        print(df[df['DISTRICT_GEOCODE'].isna()]['DISCL_SUPPLIER_ABRVNAME'].unique())

    # Show sample
    print(df[['DISCL_SUPPLIER_FULLNAME', 'DISCL_AREA_NAME', 'DISTRICT_GEOCODE']].head(10))

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv", index=False)

    # Check TRADER vs COMPANY against last year's map, and fill in missing company names

    # 2024_ritter_sport.csv - parsing probably didn't work properly
    #
    # Resolved
    # 2024_lindt_sprungli.csv - first lines of supplier_map/work/step3_located.csv
    # 2024_transparance.csv - have now filled in name manually

    # Fix Lindt Sprungli disclosures
    import pandas as pd

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv")

    df.loc[0:47, 'DISCL_TRADER_NAME'] = df.loc[0:47, 'COMPANY']
    df.loc[0:47, 'COMPANY'] = "LINDT SPRUNGLI"

    print(df[['COMPANY', 'DISCL_TRADER_NAME']].head())

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv", index=False)

    # Fix Barry Callebut disclosures 
    import pandas as pd

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv")

    df.loc[47:363, 'DISCL_TRADER_NAME'] = "BARRY CALLEBAUT AG"
    df.loc[47:363, 'COMPANY'] = "BARRY CALLEBAUT AG"

    df.to_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv", index=False)

    # Fix Ritter Sport disclosures
    df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv")

    df.loc[551:560, 'DISCL_VOLUMES'] = None
    df.loc[551:560, 'DISCL_YEAR'] = 2024
    df.loc[551:560, 'COMPANY'] = "ALFRED RITTER"
    df.loc[551:560, 'DISCL_LATITUDE'] = None
    df.loc[551:560, 'DISCL_NUMBER_FARMERS'] = None
    df.loc[551:553, 'DISCL_TRADER_NAME'] = "CEMOI"
    df.loc[553:557, 'DISCL_TRADER_NAME'] = "SUSCOM"
    df.loc[557:560, 'DISCL_TRADER_NAME'] = "CARGILL"
    df.to_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv", index=False)

    # Change column names to match the cooperative-map structure

    # Make all years 2024

    # # TRADER NAME FIXES

    # --- CLEAN TRADER NAME ----------------------------------
    # This is necessary to eventually match with custom data (and eases inspection for now) 
    #print(sorted(df['DISCL_TRADER_NAME']))
    #print(sorted(df['COMPANY']))

    # We clean names, and identify which are actual cocoa traders manually.

    # **************** THIS IS NOT ONLY FOR THE MODEL, SO LEAVE IT HERE ***********************
    # it is used to better infer the coop-level number of farmers here below, a supplier-map purpose 
    # - and it just makes the trader name variable more meaningful in the published supplier map

    # CLEANING 

    ## TRADER_NAME CREATED HERE
    df['TRADER_NAME'] = df['DISCL_TRADER_NAME']

    # Preliminary, minor cleaning of rows that have several traders separated by / (which creates one row in this case)
    # There is only one case, "Blommer/Olam", and in this case the trader is OLAM. 
    df.loc[df['TRADER_NAME'] == "Blommer/Olam", 'TRADER_NAME'] = "OLAM"

    # Manual edit of rows that come from an earlier version of the map (IS_CAM_V3)
    # Remove from the company variable names of companies that never disclosed and are there spuriously
    non_disclosing_companies = ["COCOASOURCE", "Cocoasource"]

    # View rows where COMPANY is in non_disclosing_companies
    print(df[df['COMPANY'].isin(non_disclosing_companies)])

    # Move Cocoasource to the trader name (only for rows from the earlier map)
    df.loc[(df['COMPANY'] == "COCOASOURCE") & (df['IS_CAM_V3']), 'TRADER_NAME'] = "COCOASOURCE"

    # Remove Cocoasource from the company variable (set to NaN for rows from the earlier map)
    import numpy as np
    df.loc[df['COMPANY'].isin(non_disclosing_companies) & df['IS_CAM_V3'], 'COMPANY'] = np.nan

    # Make sure Cocoasource is the trader for Tony's (only for rows from the earlier map)
    df.loc[df['COMPANY'].str.contains("TONY", case=False, na=False) & df['IS_CAM_V3'], 'TRADER_NAME'] = "COCOASOURCE"

    # Remove names of traders identified as making disclosures but which volumes spotted in customs data do not reflect total sourcing from Ivory Coast.
    # Note: this information is still available in DISCL_TRADER_NAME!

    # AND REMOVE ECOOKIM AS WELL: treat Ecookim as a source of information, not as a trader.
    # Remove COMPANY values for those identified as making disclosures, but for which volumes in customs data do not reflect total sourcing.

    non_trading_companies = [
        "ALBERT HEIJN", "ALFRED RITTER", "ALTER ECO",
        "BLOMMER", "COLRUYT",
        "ECOOKIM",
        "FERRERO", "HERSHEY",
        "MARS", "MONDELEZ", "NESTLE", "PURATOS", "RAINFOREST ALLIANCE",
        "TONY'S CHOCOLONELY", "VALRHONA"
    ]

    # Remove these companies from the COMPANY column for rows from the earlier map
    import numpy as np
    df.loc[df['COMPANY'].isin(non_trading_companies) & df['IS_CAM_V3'], 'COMPANY'] = np.nan

    # --- Code to check their volumes in customs data (commented out, for reference) ---
    # for pot_trad in sorted(df['COMPANY'].dropna().unique()):
    #     vol_tonnes = trade_data[
    #         (trade_data['EXPORTER_GROUP_CLEAN'] == pot_trad) | (trade_data['IMPORTER_GROUP_CLEAN'] == pot_trad)
    #     ]['BEAN_EQUIVALENT_VOLUME'].sum() / 1000
    #     print(f"{pot_trad}: {vol_tonnes} MT")
    # Companies found to have 0 volume are not traders. Then, it's case investigation.
    # Blommer & Hershey, see above.
    # Ferrero sources more than 200k MT in total, so it's unlikely that the 1626.6 MT found here in customs data reflect all its sourcing.
    # Ethiquable: LEAVE IT AS A TRADER, as it is actually possible that they source 150 MT, since they say they sourced 40 MT in 2014.
    # Note: Ethiquable buys from ECOOKIM in customs data, so it won't appear in sankey eventually.

    #df.to_csv('2024_coops.csv', index=False)


def step4_build_supplier_tables(DATA_DIR):
    """Fill gaps from last year's map, estimate farmer numbers, write the supplier tables."""
    import pandas as pd

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv")
    cam = pd.read_csv(f"{DATA_DIR}/supplier_map/last_year/cooperatives_2023.csv", sep=';')

    # remove need for DISCL_SUPPLIER_ABRVNAME_CLEANED, DISCL_SUPPLIER_FULLNAME_CLEANED, but check as you go that correct names are in correct place

    # Rename 2024 cooperative column names to match the cooperative-map structure

    # if the disclosing source (company) is a trader then put it there

    import pandas as pd
    import numpy as np

    # 1. Make a list of disclosing traders
    traders = [
        'ECOM', 
        'CARGILL', 
        'OFI',
        'TOUTON', 
        'ETG', 
        'BARRY CALLEBAUT AG', 
        'CEMOI VIA TRANSPARANCE COCOA'
    ]

    # 2. Iterate through traders and update
    for trader in traders:
        # Create a mask for rows where:
        # A) The trader string is found in the COMPANY column
        # B) The DISCL_TRADER_NAME column is currently empty (NaN)
    
        # Note: case=False makes it case-insensitive (e.g., finds "Cargill" for "CARGILL")
        # na=False ensures NaN values in 'COMPANY' don't crash the script
        mask = (df['COMPANY'].str.contains(trader, case=False, na=False)) & (df['DISCL_TRADER_NAME'].isna())
    
        # Apply the trader name to those specific rows
        df.loc[mask, 'DISCL_TRADER_NAME'] = trader

    # Check the results
    print(df[['COMPANY', 'DISCL_TRADER_NAME']].head())

    # Dictionary mapping the "messy" names to the "clean" names
    replacements = {
        'BARRY CALLEBAUT AG': 'BARRY CALLEBAUT',
        'BARRY CALLEBEAUT': 'BARRY CALLEBAUT',      # Fixing the typo found in your list
        'ECOM AGROTRADE LTD': 'ECOM',
        'CEMOI VIA TRANSPARANCE COCOA': 'CEMOI',
        'OLAM INTERNATIONAL LIMITED': 'OFI',
        'BLOMMER CHOCOLATE COMPANY': 'BLOMMER'        
    }

    # Apply the replacements
    df['DISCL_TRADER_NAME'] = df['DISCL_TRADER_NAME'].replace(replacements)

    # Check the results
    print(df['DISCL_TRADER_NAME'].unique())

    #df.to_csv(f'{DATA_DIR}/supplier_map/work/step3_located.csv', index=False)

    # mars, unilver, puratos, ferrero are missing trader names


    #df.to_csv(f'{DATA_DIR}/supplier_map/work/step3_located.csv', index=False)

    # Only when the step-3 helper columns are still present (they are dropped below)
    if 'DISCL_SUPPLIER_ABRVNAME_CLEANED' in df.columns:
        # Define the columns you are checking
        subset_cols = ['DISCL_SUPPLIER_ABRVNAME', 'DISCL_SUPPLIER_ABRVNAME_CLEANED', 'COMPANY', 'DISCL_TRADER_NAME', 'DISCL_SUPPLIER_FULLNAME_CLEANED', 'DISCL_LONGITUDE','DISCL_LATITUDE']

        # distinct_mask will be True for rows that are duplicates (the ones getting dropped)
        # keep='first' is the default, meaning it marks the first occurrence as False (keep) and subsequent ones as True (drop)
        dropped_rows = df[df.duplicated(subset=subset_cols, keep='first')]

        print(f"Number of rows dropped: {len(dropped_rows)}")

    for col in df.columns:
        print(f"--- {col} ---")
        print(df[col].unique())
        print("\n")

    df.DISCL_YEAR=2024

    # Only when the step-3 helper columns are still present (they are dropped below)
    if 'DISCL_SUPPLIER_ABRVNAME_CLEANED' in df.columns:
        import numpy as np

        # 1. Set Supplier Type based on whether 'WAREHOUSE' is in the name
        # We use str.contains with case=False to catch 'Warehouse', 'WAREHOUSE', etc.
        # na=False ensures NaN values are treated as False (not a warehouse)
        df['DISCL_SUPPLIER_TYPE'] = np.where(
            df['DISCL_SUPPLIER_ABRVNAME_CLEANED'].str.contains('WAREHOUSE', case=False, na=False),
            'WAREHOUSE',
            'COOPERATIVE'
        )

        # 2. If Trader Name is 'OFI', replace Supplier Abrv Name with Residual Name
        # Note: This keeps the original Supplier Abrv Name if Trader is NOT 'OFI'
        df['DISCL_SUPPLIER_ABRVNAME'] = np.where(
            df['COMPANY'] == 'OFI',
            df['CLEANED_RESIDUAL_NAME'],
            df['DISCL_SUPPLIER_ABRVNAME']
        )

        # Verify the changes

    #df.to_csv(f'{DATA_DIR}/supplier_map/work/step3_located.csv', index=False)

    # Only when the step-3 helper columns are still present (they are dropped below)
    if 'DISCL_SUPPLIER_ABRVNAME_CLEANED' in df.columns:
        df['DISCL_SUPPLIER_ABRVNAME'] = np.where(
            df['COMPANY'] == 'BARRY CALLEBAUT AG',
            df['DISCL_SUPPLIER_ABRVNAME_CLEANED'],
            df['DISCL_SUPPLIER_ABRVNAME']
        )

    # Only when the step-3 helper columns are still present (they are dropped below)
    if 'DISCL_SUPPLIER_ABRVNAME_CLEANED' in df.columns:
        # fix coop names for LINDT_SPRUNGLI
        df['DISCL_SUPPLIER_FULLNAME'] = np.where(
            df['COMPANY'] == 'LINDT SPRUNGLI',
            df['DISCL_SUPPLIER_FULLNAME_CLEANED'],
            df['DISCL_SUPPLIER_FULLNAME'])

    # List of columns to drop
    cols_to_drop = [
        'DISCL_SUPPLIER_ABRVNAME_CLEANED', 
        'DISCL_SUPPLIER_FULLNAME_CLEANED', 
        'CLEANED_RESIDUAL_NAME', 
        'DISCL_AREA_NAME_CLEAN'
    ]

    # Drop them (errors='ignore' prevents a crash if you accidentally run this cell twice)
    df.drop(columns=cols_to_drop, inplace=True, errors='ignore')

    # Verify they are gone
    print("Columns remaining:", df.columns.tolist())

    # 1. Identify the rows belonging to MARS
    is_mars = df['COMPANY'] == 'MARS'

    # 2. Create a temporary 'cleaned' series for the MARS rows
    #    We use .copy() to ensure we don't affect the original dataframe
    #    .fillna('') handles any empty values so the code doesn't crash
    cleaned_names = df.loc[is_mars, 'DISCL_SUPPLIER_ABRVNAME'].fillna('').astype(str).copy()

    # 3. Apply the cleaning rules
    #    We remove the specific terms you listed.
    #    IMPORTANT: We remove "SCOOPS" before "SCOOP" and "COOP" to avoid partial matches
    #    (e.g., preventing "SCOOPS" from becoming "S" if "COOP" was removed first)
    terms_to_remove = ["SCOOPS", "SCOOP", "COOP", "-CA", "CA", "COOP CA", "COOP-CA"]

    for term in terms_to_remove:
        # Remove the term (regex=False treats it as plain text)
        cleaned_names = cleaned_names.str.replace(term, "", regex=False)

    # 4. Remove all blank spaces
    cleaned_names = cleaned_names.str.replace(" ", "", regex=False)

    # 5. Find duplicates based on this cleaned name
    #    keep='first' marks the first instance as False (Safe) and duplicates as True (Drop)
    duplicates_mask = cleaned_names.duplicated(keep='first')

    # 6. Get the indices of the rows to drop
    indices_to_drop = duplicates_mask[duplicates_mask].index

    # 7. Drop them from the main dataframe
    df = df.drop(indices_to_drop)

    # Verify results
    print(f"Dropped {len(indices_to_drop)} duplicate MARS rows.")

    import pandas as pd
    import numpy as np

    # --- 1. Helper Function to Clean Names ---
    def get_cleaned_names(series):
        # Convert to string and handle NaNs
        clean = series.fillna('').astype(str).str.upper()
        # Remove terms (Longer terms first to avoid partial deletion issues)
        terms_to_remove = ["SCOOPS", "SCOOP", "COOP", "-CA", "CA", "COOP CA", "COOP-CA"]
        for term in terms_to_remove:
            clean = clean.str.replace(term, "", regex=False)
        # Remove all spaces
        clean = clean.str.replace(" ", "", regex=False)
        return clean

    # --- 2. Prepare the Data ---
    # Create a temporary 'MATCH_KEY' column for efficient lookup
    df['MATCH_KEY'] = get_cleaned_names(df['DISCL_SUPPLIER_ABRVNAME'])

    # Split into MARS (Target) and Non-MARS (Source)
    mars_mask = df['COMPANY'] == 'MARS'
    df_mars = df[mars_mask].copy()
    df_others = df[~mars_mask].copy()

    # --- 3. Create a Lookup Dictionary from Non-MARS Rows ---
    # We group by the clean name and take the first valid value for every column
    # This creates a "Master Record" for each supplier found in the other companies
    lookup_table = df_others.groupby('MATCH_KEY').first()

    # --- 4. Fill Missing Values in MARS Rows ---
    # We loop through columns to fill NaNs
    # Note: 'lookup_table' index is now the MATCH_KEY
    cols_to_fill = [c for c in df.columns if c not in ['COMPANY', 'MATCH_KEY']]

    for col in cols_to_fill:
        if col in lookup_table.columns:
            # Map the cleaned name to the value in the lookup table
            mapped_values = df_mars['MATCH_KEY'].map(lookup_table[col])
        
            # Fill NaN values in df_mars with the mapped values
            df_mars[col] = df_mars[col].fillna(mapped_values)

    # --- 5. Update the Original DataFrame ---
    # Update the original df with the filled MARS rows
    df.loc[mars_mask] = df_mars

    # Drop the temporary key column
    df.drop(columns=['MATCH_KEY'], inplace=True)

    # Verify
    print("Missing values filled using cross-company matches.")
    # Show a sample check: Rows that are MARS and have a Latitude filled (assuming it was missing before)
    print(df[df['COMPANY'] == 'MARS'][['DISCL_SUPPLIER_ABRVNAME', 'DISCL_LATITUDE']].head())

    #df.to_csv(f'{DATA_DIR}/supplier_map/work/step3_located.csv', index=False)

    # Create a mask for the specific company
    mask_bc = df['COMPANY'] == "BARRY CALLEBAUT AG"

    # Replace " WAREHOUSE" with an empty string for those rows
    # regex=False ensures it treats " WAREHOUSE" as literal text
    df.loc[mask_bc, 'DISCL_SUPPLIER_ABRVNAME'] = df.loc[mask_bc, 'DISCL_SUPPLIER_ABRVNAME'].str.replace(" WAREHOUSE", "", regex=False)

    # Verify a few examples
    print(df.loc[mask_bc, ['COMPANY', 'DISCL_SUPPLIER_ABRVNAME']].head())

    # match column names to last year's map (cooperatives_2023.csv)

    import pandas as pd

    df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step3_located.csv")

    # Add Mars' 2024 update: cooperatives not yet listed for Mars become new
    # rows (short name only; region and full name are filled from last year's
    # map below, as for the other rows)
    mars_24 = pd.read_csv(f"{DATA_DIR}/supplier_map/company_disclosures_2024/mars_2024_update.csv")
    for col in mars_24.columns:
        if pd.api.types.is_string_dtype(mars_24[col]):
            mars_24[col] = mars_24[col].str.replace('"', '', regex=False).str.strip()
    # keep only well-formed 2024 rows (a few are shifted by stray quotes)
    mars_24 = mars_24[(pd.to_numeric(mars_24['DISCL_YEAR'], errors='coerce') == 2024)
                      & ~mars_24['DISCL_SUPPLIER_ABRVNAME'].str.fullmatch(r'[\d.]+', na=True)]

    def simplified(series):
        """Short name in a simplified form: upper case, without COOP / SCOOP / CA and spaces."""
        out = series.fillna('').astype(str).str.upper()
        for term in ["SCOOPS", "SCOOP", "COOP", "-CA", "CA", "COOP CA", "COOP-CA"]:
            out = out.str.replace(term, "", regex=False)
        return out.str.replace(" ", "", regex=False)

    known = set(simplified(df.loc[df['COMPANY'] == 'MARS', 'DISCL_SUPPLIER_ABRVNAME']))
    new_rows = mars_24[~simplified(mars_24['DISCL_SUPPLIER_ABRVNAME']).isin(known)]
    new_rows = new_rows[~simplified(new_rows['DISCL_SUPPLIER_ABRVNAME']).duplicated()]
    new_rows = new_rows.assign(DISCL_YEAR=2024, COMPANY='MARS')
    df = pd.concat([df, new_rows], ignore_index=True)
    print(f"Added {len(new_rows)} cooperatives from Mars' 2024 update.")

    # 1. Define a mapping for columns that exist in both but have different names.
    column_mapping = {
        'DISCL_YEAR': 'YEAR',
        'DISCL_AREA_NAME':'DISTRICT_NAME', 
        'DISCL_TRADER_NAME': 'TRADER_NAMES',
        'DISCL_NUMBER_FARMERS': 'TOTAL_FARMERS',
        'DISCL_LATITUDE':'LATITUDE',
        'DISCL_LONGITUDE':'LONGITUDE'
    }

    # 2. Rename the columns in df
    df = df.rename(columns=column_mapping)

    # 3. Reindex df to match cam exactly
    # This adds missing columns (filled with NaN), drops extras, and fixes the order.
    # Keep what each 2024 disclosure says - who disclosed, the trader, the number
    # of farmers - in their own columns. The cells below fill gaps in the other
    # columns from the 2023 map; these three must stay as disclosed so that
    # farmer numbers can be estimated per link (further down).
    disclosure_2024 = df[['COMPANY', 'TRADER_NAMES', 'TOTAL_FARMERS']].copy()
    df = df.reindex(columns=cam.columns)
    df['DISCL_COMPANY'] = disclosure_2024['COMPANY'].values
    df['DISCL_TRADER_NAME'] = disclosure_2024['TRADER_NAMES'].values
    df['DISCL_NUMBER_FARMERS'] = disclosure_2024['TOTAL_FARMERS'].values

    df.SUPPLIER_ABRVNAME, df.SUPPLIER_FULLNAME = df.DISCL_SUPPLIER_ABRVNAME, df.DISCL_SUPPLIER_FULLNAME
    df.COOP_ID = df.index

    # Verify the result
    print("Columns match:", df.columns.equals(cam.columns))

    df.to_csv(f'{DATA_DIR}/supplier_map/work/step4_last_year_format.csv', index=False)

    import pandas as pd

    # 1. LOAD DATA
    new_df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step4_last_year_format.csv")
    old_df = pd.read_csv(f"{DATA_DIR}/supplier_map/last_year/cooperatives_2023.csv", sep=';', na_values=['NA', 'nan', ''])

    # 2. FILTER OLD DATA
    old_df = old_df[old_df.YEAR == 2023]

    # 3. DEFINE THE MATCHING KEY
    join_key = 'SUPPLIER_ABRVNAME'

    # Clean the key column (remove extra spaces) to ensure matches work
    new_df[join_key] = new_df[join_key].astype(str).str.strip()
    old_df[join_key] = old_df[join_key].astype(str).str.strip()

    # 4. IMPUTE MISSING VALUES
    # Identify columns that exist in both files
    common_cols = [col for col in new_df.columns if col in old_df.columns and col != join_key]

    print(f"Imputing data based on key: {join_key}...")

    # Create a reference dictionary from the old dataframe (remove duplicates to keep unique keys)
    old_df_clean = old_df.dropna(subset=[join_key]).drop_duplicates(subset=[join_key])

    for col in common_cols:
        # Check how many empty values we have before filling
        missing_before = new_df[col].isna().sum()
    
        # Create a map: { 'Supplier Name' : 'Old Value' }
        mapping = old_df_clean.set_index(join_key)[col]
    
        # Fill NaN values in the new_df using the map
        new_df[col] = new_df[col].fillna(new_df[join_key].map(mapping))
    
        # Check improvements
        missing_after = new_df[col].isna().sum()
        filled_count = missing_before - missing_after
    
        if filled_count > 0:
            print(f"  -> Filled {filled_count} missing values in column '{col}'")

    # --- NEW STEP: Fill any remaining NaN values with 'NA' ---
    new_df.REPEATED_FROM_PAST_YEAR = 'NA'
    new_df = new_df.fillna('NA')

    # 5. SAVE THE RESULT
    output_csv_path = f'{DATA_DIR}/supplier_map/work/step4_gaps_filled.csv'
    new_df.to_csv(output_csv_path, sep=';', index=False, na_rep='NA')

    print(f"\nSuccess! Imputed file saved to: {output_csv_path}")

    import pandas as pd

    # 1. LOAD DATA
    new_df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step4_gaps_filled.csv",sep=';', na_values=['NA', 'nan', ''])
    old_df = pd.read_csv(f"{DATA_DIR}/supplier_map/last_year/cooperatives_2023.csv", sep=';', na_values=['NA', 'nan', ''])

    # 2. FILTER OLD DATA
    old_df = old_df[old_df.YEAR == 2023]

    # 3. DEFINE THE MATCHING KEY
    join_key = 'SUPPLIER_FULLNAME'

    # Clean the key column (remove extra spaces) to ensure matches work
    new_df[join_key] = new_df[join_key].astype(str).str.strip()
    old_df[join_key] = old_df[join_key].astype(str).str.strip()

    # 4. IMPUTE MISSING VALUES
    # Identify columns that exist in both files
    common_cols = [col for col in new_df.columns if col in old_df.columns and col != join_key]

    print(f"Imputing data based on key: {join_key}...")

    # Create a reference dictionary from the old dataframe (remove duplicates to keep unique keys)
    old_df_clean = old_df.dropna(subset=[join_key]).drop_duplicates(subset=[join_key])

    for col in common_cols:
        # Check how many empty values we have before filling
        missing_before = new_df[col].isna().sum()
    
        # Create a map: { 'Supplier Name' : 'Old Value' }
        mapping = old_df_clean.set_index(join_key)[col]
    
        # Fill NaN values in the new_df using the map
        new_df[col] = new_df[col].fillna(new_df[join_key].map(mapping))
    
        # Check improvements
        missing_after = new_df[col].isna().sum()
        filled_count = missing_before - missing_after
    
        if filled_count > 0:
            print(f"  -> Filled {filled_count} missing values in column '{col}'")

    # --- NEW STEP: Fill any remaining NaN values with 'NA' ---
    new_df.REPEATED_FROM_PAST_YEAR = 'NA'
    new_df = new_df.fillna('NA')

    # 5. SAVE THE RESULT
    output_csv_path = f'{DATA_DIR}/supplier_map/work/step4_gaps_filled.csv'
    new_df.to_csv(output_csv_path, sep=';', index=False, na_rep='NA')

    print(f"\nSuccess! Imputed file saved to: {output_csv_path}")

    new_df = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step4_gaps_filled.csv",sep=';', na_values=['NA', 'nan', ''])

    new_df.drop(columns="COOP_ID", inplace=True)

    # Farmer numbers ------------------------------------------------------------
    # Number of farmers per cooperative-buyer link (docs/HOW_THE_MODEL_WORKS.md, Step 5):
    #   1. the buyer's own disclosed figure (2024; if none, its earlier figures
    #      for this cooperative)
    #   2. otherwise the mean of the figures of other buyers of the same
    #      cooperative (2024 first, then earlier years)
    #   3. otherwise left empty: the model then draws a size from all disclosed
    #      sizes, i.e. on average the overall mean link size
    # Cooperatives are matched across years by acronym (SUPPLIER_ABRVNAME), using
    # only acronyms that belong to a single cooperative in the 2023 map.
    import sys, os
    from supplier_map_tools import impute_farmer_numbers

    past = pd.read_csv(f"{DATA_DIR}/supplier_map/last_year/links_2023.csv", sep=';',
                       na_values=['NA', 'nan', ''], low_memory=False)
    past = past[past['REPEATED_FROM_PAST_YEAR'] != True]          # real disclosures only
    n_coops = past.groupby('SUPPLIER_ABRVNAME')['COOP_ID'].nunique()
    history = past[past['SUPPLIER_ABRVNAME'].isin(n_coops[n_coops == 1].index)].rename(
        columns={'DISCLOSURE_SOURCE': 'DISCL_COMPANY', 'TRADER_NAME': 'DISCL_TRADER_NAME'})

    estimated = impute_farmer_numbers(
        new_df, coop_col='SUPPLIER_ABRVNAME', year_col='YEAR',
        company_col='DISCL_COMPANY', trader_col='DISCL_TRADER_NAME',
        disclosed_col='DISCL_NUMBER_FARMERS', history=history)
    new_df['NUM_FARMERS'] = estimated['NUM_FARMERS'].values
    new_df['NUM_FARMERS_EXTRAPOLATED'] = estimated['NUM_FARMERS_EXTRAPOLATED'].values
    # ---------------------------------------------------------------------------

    print(len(new_df))
    # de-duplicate, ignoring the per-disclosure columns above (they would
    # otherwise keep duplicates apart)
    LINK_LEVEL_COLUMNS = ['DISCL_COMPANY', 'DISCL_TRADER_NAME', 'DISCL_NUMBER_FARMERS',
                          'NUM_FARMERS', 'NUM_FARMERS_EXTRAPOLATED']
    new_df.drop_duplicates(subset=[c for c in new_df.columns if c not in LINK_LEVEL_COLUMNS], inplace=True)
    print(len(new_df))

    new_df.reset_index(drop=True, inplace=True)

    # Insert the new COOP_ID at the very beginning (position 0)
    new_df.insert(0, 'COOP_ID', new_df.index)

    # Save the file
    # na_rep='NA' ensures empty values are saved as 'NA' instead of empty strings
    new_df.to_csv(output_csv_path, sep=';', index=False, na_rep='NA')

    # The file I have made matches the structure of cam_coopyear. Make a second file with flow ids (i.e. with format of cam_long)

    # REMOVE DUPLICATES -----------------------------
    # At this point, within a year, several rows can reflect the same coop obviously 
    # (as several companies may have disclosed to buy from the same coop), 
    # but also the same link can come from different sources of disclosure data - typically, the previous CAM and data scraped by UCLouvain team). 

    # We thus remove duplicates (i.e. make row ids) in 2 different ways: 
    # 1- one row per coop per year (aggregating across links) - which is what we publish 
    # 2- one row per actual link (aggregating across sources) - which is what the model reads. 

    # (we DON'T try to make one row per sourcing flow (links to several companies that are on different stages of the supply chain are merged))

    coops_24 = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step4_gaps_filled.csv",sep=';', na_values=['NA', 'nan', ''])

    print(len(coops_24))
    LINK_LEVEL_COLUMNS = ['DISCL_COMPANY', 'DISCL_TRADER_NAME', 'DISCL_NUMBER_FARMERS',
                          'NUM_FARMERS', 'NUM_FARMERS_EXTRAPOLATED']
    civ_coopyear = coops_24.drop(columns=LINK_LEVEL_COLUMNS, errors='ignore').drop_duplicates(subset='SUPPLIER_ABRVNAME')
    print(len(civ_coopyear))

    civ_coopyear.to_csv(f"{DATA_DIR}/supplier_map/work/step4_cooperatives.csv", sep=';', index=False, na_rep='NA')

    import pandas as pd
    import numpy as np

    # Load source data
    cam_long_23 = pd.read_csv(f"{DATA_DIR}/supplier_map/last_year/links_2023.csv", sep=';', na_values=['NA', 'nan', ''])

    # Create a copy to avoid SettingWithCopy warnings
    links_table = coops_24.copy()

    links_table = links_table.replace(r'^\s*$', np.nan, regex=True)

    # 1. Handle ABRVNAME (fill in both directions)
    links_table['SUPPLIER_ABRVNAME'] = links_table['SUPPLIER_ABRVNAME'].fillna(links_table['DISCL_SUPPLIER_ABRVNAME'])
    links_table['SUPPLIER_ABRVNAME'] = links_table['SUPPLIER_ABRVNAME'].fillna(links_table['SUPPLIER_FULLNAME'])
    links_table['SUPPLIER_ABRVNAME'] = links_table['SUPPLIER_ABRVNAME'].fillna(links_table['DISCL_SUPPLIER_FULLNAME'])
    links_table['DISCL_SUPPLIER_ABRVNAME'] = links_table['DISCL_SUPPLIER_ABRVNAME'].fillna(links_table['SUPPLIER_ABRVNAME'])

    # 2. Handle FULLNAME (fill in both directions)
    links_table['SUPPLIER_FULLNAME'] = links_table['SUPPLIER_FULLNAME'].fillna(links_table['DISCL_SUPPLIER_FULLNAME'])
    links_table['SUPPLIER_FULLNAME'] = links_table['SUPPLIER_FULLNAME'].fillna(links_table['SUPPLIER_ABRVNAME'])
    links_table['SUPPLIER_FULLNAME'] = links_table['SUPPLIER_FULLNAME'].fillna(links_table['DISCL_SUPPLIER_ABRVNAME'])
    links_table['DISCL_SUPPLIER_FULLNAME'] = links_table['DISCL_SUPPLIER_FULLNAME'].fillna(links_table['SUPPLIER_FULLNAME'])

    print(links_table.columns)

    # --- 1. Create BUYER Variable ---
    links_table['BUYER'] = np.where(
        (links_table['TRADER_NAMES'].isna()) & (links_table['DISCLOSURE_SOURCES'] != "RAINFOREST ALLIANCE"),
        links_table['DISCLOSURE_SOURCES'],
        links_table['TRADER_NAMES']
    )

    # --- 2. Handle Certifications ---
    def aggregate_certs(series):
        items = []
        for x in series:
            if isinstance(x, list):
                items.extend(x)
            elif pd.notna(x):
                items.append(x)
        unique_items = sorted(list(set(items)))
        return " + ".join(unique_items)

    links_table['CERTIFICATIONS'] = links_table.groupby(['COOP_ID', 'YEAR', 'BUYER'])['DISCL_CERTIFICATION_NAME'].transform(aggregate_certs)

    # --- 3. Distinct (Slice the first row per group) ---
    links_table = links_table.drop_duplicates(
        subset=['COOP_ID', 'YEAR', 'BUYER'], 
        keep='first'
    )

    # --- 4. Create FLOW_ID ---
    links_table['row_num'] = links_table.groupby('YEAR').cumcount() + 1
    links_table['FLOW_ID'] = links_table['YEAR'].astype(str) + "-" + links_table['row_num'].astype(str)

    # --- 5. Select and Drop Columns ---
    cert_cols = [c for c in links_table.columns if c.startswith('CERT_') and c != 'CERTIFICATIONS']
    cols_to_drop = [
        'DISCL_TRADER_NAME', 'LOCALITY_NAME', 'CAM_BUYERS', 'NOT_RFA',
        'unique_company_link', 'unique_trader_link', 'row_num',
        'DISCL_COMPANY', 'DISCL_NUMBER_FARMERS'   # helper columns of the farmer-number step
    ] + cert_cols

    links_table = links_table.drop(columns=[c for c in cols_to_drop if c in links_table.columns])

    links_table['COMPANY'] = links_table['DISCLOSURE_SOURCES']

    # (NUM_FARMERS was estimated per disclosure further up; see "Farmer numbers".)

    # --- 6. Reorder Columns ---
    front_cols = [
        'FLOW_ID', 'COOP_ID', 'YEAR', 'SUPPLIER_ABRVNAME', 'SUPPLIER_FULLNAME', 
        'LATITUDE', 'LONGITUDE', 'DISTRICT_NAME', 'DISTRICT_GEOCODE',
        'BUYER', 'COMPANY', 'TRADER_NAMES', 'CERTIFICATIONS',
        'NUM_FARMERS', 'NUM_FARMERS_EXTRAPOLATED',
        'TOTAL_FARMERS_NONTRADER', 'TOTAL_FARMERS_TRADER', 'TOTAL_FARMERS_RFA', 'TOTAL_FARMERS'
    ]

    # Append remaining columns that are not in front_cols
    remaining_cols = [c for c in links_table.columns if c not in front_cols]
    links_table = links_table[front_cols + remaining_cols]

    links_table['IS_TRADER'] = links_table['DISCLOSURE_SOURCES'] == links_table['TRADER_NAMES']
    links_table['LVL_4_NAME'] = links_table['DISTRICT_GEOCODE']

    links_table.to_csv(f"{DATA_DIR}/supplier_map/work/step4_links.csv", sep=';', index=False, na_rep='NA')


def step5_write_standard_tables(DATA_DIR):
    """Convert the two supplier tables to the model's standard format."""
    import pandas as pd
    links = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step4_links.csv", sep=';',
                        na_values=['NA', ''], keep_default_na=True)
    suppliers = pd.read_csv(f"{DATA_DIR}/supplier_map/work/step4_cooperatives.csv", sep=';',
                            na_values=['NA', ''], keep_default_na=True)
    out_dir = f"{DATA_DIR}/supplier_map"
    os.makedirs(out_dir, exist_ok=True)
    standard_links = pd.DataFrame({
        'SUPPLIER_NUMBER': links['COOP_ID'],
        'YEAR': links['YEAR'],
        'REGION_CODE': links['DISTRICT_GEOCODE'],
        'SUPPLIER_SHORT_NAME': links['SUPPLIER_ABRVNAME'],
        'SUPPLIER_NAME': links['SUPPLIER_FULLNAME'],
        'BUYER': links['BUYER'],
        'BUYER_IS_TRADER': links['TRADER_NAMES'].notna(),
        'NUMBER_OF_FARMERS': links['NUM_FARMERS'],
        'CERTIFICATIONS': links['CERTIFICATIONS'],
        'CERTIFIED': links['CERTIFIED'],
        'LINK_ID': links['FLOW_ID'],
        'DISCLOSED_BY': links['DISCLOSURE_SOURCES'],
    })
    standard_suppliers = pd.DataFrame({
        'SUPPLIER_NUMBER': suppliers['COOP_ID'],
        'YEAR': suppliers['YEAR'],
        'REGION_CODE': suppliers['DISTRICT_GEOCODE'],
        'SUPPLIER_SHORT_NAME': suppliers['SUPPLIER_ABRVNAME'],
        'SUPPLIER_NAME': suppliers['SUPPLIER_FULLNAME'],
        'CERTIFICATIONS': suppliers['CERTIFICATIONS'],
        'CERTIFIED': suppliers['CERTIFIED'],
    })
    standard_links.to_csv(f"{out_dir}/supplier_links_2024.csv", index=False)
    standard_suppliers.to_csv(f"{out_dir}/suppliers_2024.csv", index=False)
    print(f"wrote {out_dir}/supplier_links_2024.csv ({len(standard_links)} rows)")
    print(f"wrote {out_dir}/suppliers_2024.csv ({len(standard_suppliers)} rows)")


STEPS = [step1_standardise_disclosures, step2_combine_and_align_columns,
         step3_clean_match_and_locate, step4_build_supplier_tables,
         step5_write_standard_tables]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    default = os.path.abspath(os.path.join(here, '..', 'data', 'synthetic_raw_inputs'))
    p = argparse.ArgumentParser(description="Build the Côte d'Ivoire 2024 supplier map.")
    p.add_argument('--data-dir', default=os.environ.get('MODEL_DATA_DIR', default))
    p.add_argument('--from-step', type=int, default=1, choices=range(1, 6))
    p.add_argument('--to-step', type=int, default=5, choices=range(1, 6))
    a = p.parse_args()
    os.makedirs(os.path.join(a.data_dir, 'supplier_map', 'work', 'step1_by_company'), exist_ok=True)
    for n, step in enumerate(STEPS, start=1):
        if a.from_step <= n <= a.to_step:
            print(f"\n=== Step {n}: {step.__doc__}")
            step(a.data_dir)


if __name__ == '__main__':
    main()
