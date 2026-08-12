# Tool to Combine Your Own Cooperative Data with the Trase Cocoa Cooperatives Dataset

This open-source Python tool allows users to integrate their own cooperative disclosure data with the official Trase cooperative base map for Côte d'Ivoire.

* [Trase Côte d'Ivoire Cocoa Cooperative Map](https://trase.earth/explore/facilities-data/map?facilityTypeId=cote-d-ivoire-cocoa-cooperatives)

It takes a standard CSV of cooperative disclosures for cooperatives in Côte d'Ivoire, cleans and normalizes the text, and performs fuzzy matching against the official Trase GeoJSON. It updates existing cooperatives by appending the disclosing buyer, and geographically processes brand-new cooperatives by assigning them to the correct administrative departments before adding them to the map.

## Sourcing and Preparing New Cooperative Data

Many major cocoa buyers publish their cooperative supply chain data annually. We encourage you to use this tool to integrate the latest available information into the Trase cooperative map.

**1. Where to find data**
You can usually extract this data from company sustainability dashboards, direct CSV downloads, or annual supply chain reports. For example:
* [Barry Callebaut Traceability Dashboard](https://www.barry-callebaut.com/en-SE/sustainability/our-sustainable-raw-materials/transparency-and-traceability-our-cocoa-supply-chain)
* [Nestlé Responsible Sourcing Disclosure (PDF)](https://www.nestle.com/sites/default/files/2025-09/responsible-sourcing-disclosure-cocoa.pdf)

**2. Formatting your data**
To use the code in this directory, you must format the information you find online so it matches our **Input Data Schema** (detailed below). Standardizing your column headers ensures your data can be seamlessly merged with the existing Trase dataset. 

**3. Expanding to other countries**
While this specific tool is configured for Côte d'Ivoire, you can adapt the codebase to map supply chains in other countries simply by swapping out the Trase base map and the administrative boundaries file (`ci_departments.geojson`).

### Required Base Files and Data Sources

Both required `.geojson` reference files are **included in this repository by default** inside the `data/` folder, pre-populated with the latest Trase cocoa cooperatives data release (as of August 2026).

* **`ci_departments.geojson`**
Included in the repository. Provides the official administrative boundaries for Côte d'Ivoire used for spatial joins.
* **`cote-d-ivoire-cocoa-cooperatives.geojson`**
Included in the repository (most recent data as of August 2026).
* **Updating the Base Map:** If you wish to fetch a newer version of the base map in the future, visit the [Trase Cocoa Cooperatives Map](https://trase.earth/explore/facilities-data/map?facilityTypeId=cote-d-ivoire-cocoa-cooperatives) and click the **Download** button. Save the downloaded GeoJSON file into your local `data/` directory using the same filename.

## Folder Structure

Before running the script, ensure your working directory is structured exactly like this:

```text
my_project/
├── update_trase_coops.py
├── requirements.txt
└── data/
    ├── user_disclosure.csv                      <-- Your data
    ├── cote-d-ivoire-cocoa-cooperatives.geojson <-- Trase Base Map
    └── ci_departments.geojson                   <-- Ivorian Departments Reference Map

```

## Installation & Prerequisites

1. Ensure you have Python 3.8+ installed.
2. Install the required packages by running:
```bash
pip install -r requirements.txt

```
## Input Data Schema (`user_disclosure_data.csv`)

For the script to successfully process your cooperative disclosures, your CSV file **must** include specific columns. Column names are case-insensitive, but the following standard headers are highly recommended:

| Column Name | Data Type | Required? | Description |
| --- | --- | --- | --- |
| **`SUPPLIER_FULLNAME`** | String | Yes* | The full, official name of the cooperative (e.g., *COOPERATIVE AGRICOLE BACON ESPOIR*). |
| **`SUPPLIER_ABRVNAME`** | String | Yes* | The short or abbreviated name of the cooperative (e.g., *CABES*). |
| **`COMPANY`** | String | Yes | The name of the buyer, trader, or manufacturer disclosing this cooperative (e.g., *NESTLE*). *(Alternative accepted header: `BUYER`)* |
| **`LATITUDE`** | Float | Yes** | The Y-coordinate (e.g., `6.356`). |
| **`LONGITUDE`** | Float | Yes** | The X-coordinate (e.g., `-3.909`). |
| **`YEAR`** | Integer | No | The disclosure year for the cooperative flow. If left blank, the script will fall back to the --fallback-year provided in the terminal. |

> **Notes on Requirements:**
> * **\*** You must provide **at least one** naming column (`SUPPLIER_FULLNAME` or `SUPPLIER_ABRVNAME`). If both are provided, the script will prioritize the full name for matching.
> * **\*\*** Coordinates (`LATITUDE` / `LONGITUDE`) are **only strictly required if the cooperative does not already exist** in the Trase base map. If the script cannot find a match and coordinates are missing, that cooperative will be skipped.

---

### Example Dataset (`example_user_disclosure_data.csv`)

There is an example version of `user_disclosure_data.csv` provided in the `data` folder, named `example_user_disclosure_data.csv`. 

This example file includes several common data scenarios and formatting quirks to demonstrate how the script handles them automatically:

*   **Row 1 (`OUBE`) — Tests a Roll-Forward:** This cooperative exists in the base map for 2019, but here it is reported for 2024 without coordinates. The script will safely copy the 2019 location data and create a new 2024 point with "CHOCO CORP" added to the buyers list.
*   **Row 2 (`2 AD`) — Tests an Exact Match:** This exactly matches ID 2 for the year 2019 in the base map. The script will simply append "CHOCO CORP" to its existing 2019 entry.
*   **Row 3 (`CNF`) — Tests a Brand New Cooperative:** This does not exist in the base map. The script will use the coordinates to calculate its department, assign it a brand new ID, and plot it on the map for 2024.
*   **Row 4 (`2A SCCOPS`) — Tests Fuzzy Matching:** The official name is "COOPERATIVE LES AGRICULTEURS D'AKOUPE", but here there is a slight typo/variation. The script catches the typo dynamically and maps it successfully to ID 3.
*   **Row 5 (`EPO`) — Tests the French Comma Bug:** This is a brand new cooperative, but the coordinates use commas instead of decimals (`6,150`, `-7,250`). The script automatically fixes the formatting and plots it correctly.

## How to Run

Once your `data/` folder is populated with the three required files, navigate to the project directory in your terminal and run:

```bash
python create_updated_trase_cooperatives_geojson.py --fallback-year 2026
```

If your file is not named user_disclosure_data.csv, the script will automatically pause and prompt you to type in the correct filename.

## Output

The script will generate a new file in your `data/` directory named:
`updated_trase_coops_with_user_data.geojson`

This file is a ready-to-use spatial dataset containing:

1. All original Trase CIV cooperatives.
2. Updated `buyers_list` arrays for cooperatives you disclosed.
3. Brand new spatial point features for cooperatives unique to your dataset, fully populated with their corresponding Department IDs via point-in-polygon spatial joining.
