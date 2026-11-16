# =============================================================================
# clean the 2024 Côte d'Ivoire customs export records
# =============================================================================
# Reads and writes files under MODEL_DATA_DIR (see input_preparation/setup.R).
#
# Input : <DATA_DIR>/customs/raw/CIV_2024_all_one_sheet.xlsx  (raw customs
#         records, one row per shipment; licensed data, NOT included)
#         <DATA_DIR>/customs/ISO2_ENGLISH_COUNTRY_NAMES.csv          (country list)
# Output: <DATA_DIR>/customs/cocoa_exports_2024.csv  (the model input)
#
# Main steps: rename columns to the model's conventions, translate French country
# names, convert CFA values to USD where needed, derive HS6 and tonnes, flag and
# fix price/volume outliers, and run upload checks.
# Note: this script is interactive in places (it prints tables for manual
# review). There is a placeholder near the end for fixing individual shipments
# by SHPMT_ID, if your own data need it.
# =============================================================================

# Script to pre-process 2024 IVORY COAST CDs

# Author: Valentin Guye & Niamh French

# Workstation set up ------------------------------------------------------


library(tidyverse)
library(readxl)
library(stringi)
library(dplyr)
library(stringr)
library(countrycode) # necessary because country names are in French in cd data. 


# preventing scientific formatting
options(scipen = 9999)

# Load helper functions (for upload)
source(file.path("input_preparation", "setup.R"))   # paths, str_trans(), prepare_data_for_upload()

WRITE_OUTPUT <- TRUE


# Load data ---------------------------------------------------
cd_df <- 
  read_excel(require_input(input_path("customs", "raw", "CIV_2024_all_one_sheet.xlsx")),
             col_types = "text")

cd_df_original <- cd_df

# Give an id to shipments, to ease and make more robust manual imputations
cd_df$SHPMT_ID <- 1:nrow(cd_df)

cd_df <- cd_df %>% rename(COUNTRY_OF_DESTINATION = DESTINATION, 
                          HS_CODE = SH,
                          HS_CODE_DESCRIPTION = "COMMERCIAL PRODUCT DESC",
                          CIF_USD = "CIF VALUE",
                          FOB_VALUE = "FOB VALUE",
                          BUYER = SUPPLIER,
                          EXPORTER_TAX_ID = IMMIMP,
                          NET_WEIGHT_KG = "NET WEIGHT",
                          GROSS_WEIGHT_KG = "GROSS WEIGHT",
                          COUNTRY_OF_ORIGIN = ORIGINE,
                          NUMBER_OF_PRODUCTS = QUANTITY,
                          TRANSPORT_MODE = "TRANSPORT MODE")

head(cd_df)

# Country name --------------------------------

# Translate country names to English
# Benchmark process_cote_divoire_2019.R were it is applied to the country of destination. 
# use countrycode::countryname() because no country code available to use "world/metadata/global/country_name_dictionaries/ISO2_ENGLISH_COUNTRY_NAMES.csv",
# Requires to do it before stri_trans_toupper because increases ambiguous cases in countryname()
#countryname(unique(cd_df$COUNTRY_OF_DESTINATION))

cd_df <-
  cd_df %>% 
  mutate(
    COUNTRY_OF_DESTINATION = fn_fr_to_en_country_names(COUNTRY_OF_DESTINATION), 
    COUNTRY_OF_ORIGIN = fn_fr_to_en_country_names(COUNTRY_OF_ORIGIN), 
    
    COUNTRY_OF_DESTINATION = case_when(
      # Use str_trim() to remove whitespace before matching
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "COTE D LVOIRE") ~ "COTE D'IVOIRE",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "SENGAL") ~ "SENEGAL",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "S. AFRICA") ~ "SOUTH AFRICA",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "ESTONIE") ~ "ESTONIA",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "Coree") ~ "SOUTH KOREA",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "Republique de (Coree du Sud)") ~ "SOUTH KOREA",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "Nouvelle-Zelande") ~ "NEW ZEALAND",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "SINGAPOUR") ~ "SINGAPORE",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "SUISSE") ~ "SWITZERLAND",
      str_detect(toupper(str_trim(COUNTRY_OF_DESTINATION)), "TUNISIE") ~ "TUNISIA",
      toupper(str_trim(COUNTRY_OF_DESTINATION)) == "PLUSIEURS" ~ "MANY", 
      TRUE ~ str_trim(COUNTRY_OF_DESTINATION) # Also trim all other names
    ),
    
    COUNTRY_OF_ORIGIN = case_when(
      # Use str_trim() to remove whitespace before matching
      str_detect(toupper(str_trim(COUNTRY_OF_ORIGIN)), "COTE D LVOIRE") ~ "COTE D'IVOIRE",
      TRUE ~ str_trim(COUNTRY_OF_ORIGIN) # Also trim all other names
    ),

    # Explicitly set "Unknown" to NA to avoid the warning
    COUNTRY_OF_DESTINATION_ISO2C = case_when(
      COUNTRY_OF_DESTINATION == "Unknown" ~ NA_character_,
      TRUE ~ countryname(COUNTRY_OF_DESTINATION, "iso2c")
    ),
    
    
    COUNTRY_OF_ORIGIN_ISO2C = case_when(
      COUNTRY_OF_ORIGIN == "Unknown" ~ NA_character_,
      TRUE ~ countryname(COUNTRY_OF_ORIGIN, "iso2c")
    )
    #PROVENANCE_COUNTRY_ISO2C = countryname(PROVENANCE_COUNTRY, "iso2c")
  )
unique(cd_df$COUNTRY_OF_DESTINATION_ISO2C)
unique(cd_df$COUNTRY_OF_ORIGIN_ISO2C)
unique(cd_df$COUNTRY_OF_ORIGIN)

iso2_dic <-
  read.csv2(require_input(input_path("customs", "ISO2_ENGLISH_COUNTRY_NAMES.csv")), na.strings = "NNN") %>%
  mutate_all(as.character) %>%
  as_tibble()

# Get unique, non-NA codes from your data
codes_in_data <- unique(na.omit(cd_df$COUNTRY_OF_DESTINATION_ISO2C))

# Get unique, non-NA codes from your dictionary
codes_in_dict <- unique(na.omit(iso2_dic$ISO2))

# Find the codes in your data that are NOT in the dictionary
unmatched_codes <- setdiff(codes_in_data, codes_in_dict)

# Check if there are any unmatched codes and print them
if (length(unmatched_codes) > 0) {
  print("Error: The following COUNTRY_OF_DESTINATION_ISO2C codes were not found in iso2_dic:")
  print(unmatched_codes)
  
  stop("Not all countries matched. See printed list above.")
}

# If the script continues, you know all codes matched.
# You can now run your join pipeline safely.
cd_df <-
  left_join(cd_df, iso2_dic, by = c("COUNTRY_OF_DESTINATION_ISO2C" = "ISO2")) %>%
  mutate(COUNTRY_OF_DESTINATION = case_when(
    COUNTRY_OF_DESTINATION != "Unknown" ~ COUNTRY, 
    TRUE ~ "Unknown"
  )) %>% 
  select(-COUNTRY)

cd_df <-
  left_join(cd_df, iso2_dic, by = c("COUNTRY_OF_DESTINATION_ISO2C" = "ISO2")) %>%
  mutate(COUNTRY_OF_DESTINATION = case_when(
    COUNTRY_OF_DESTINATION != "Unknown" ~ COUNTRY, 
    TRUE ~ "Unknown"
  )) %>% 
  select(-COUNTRY)

if (any(is.na(cd_df$COUNTRY_OF_DESTINATION))) {
  stop("Not all countries matched")
}
# rm(iso2_dic)


# Standardize --------------------------------------

# remove foreign characters from column names
colnames(cd_df) <- stri_trans_general(colnames(cd_df), "Latin-ASCII")

# remove special characters
str_trans <- function(x) {
  x %>%
    stri_trans_toupper() %>%
    stri_trans_general("Latin-ASCII")
}
cd_df <-
  cd_df %>%
  mutate_if(is.character, str_trans)


# remove any semicolons or end-of-line characters in data
rm_problem_characters <- function(x) {
  gsub(';|\r|\t|\n|"', "", x) # note that '"' needs to be removed, to pass check for export 
}
cd_df <-
  cd_df %>%
  mutate_if(is.character, rm_problem_characters)
if (any(map_lgl(cd_df, ~ any(grepl(';|\r|\t|\n|"', .x))))) {
  stop("Problem characters remain")
}


## remove all empty rows

# get vector of rows with all NA, then invert with '!'
rows_to_keep <- !apply(cd_df, 1, function(x) all(is.na(x)))
# subset based on empty rows from previous line
cd_df <- cd_df[rows_to_keep, ]


# ensure leading zeros in HS10 field 
if(!all(nchar(cd_df$HS_CODE)==10)){
  stop("Check the HS_CODE variable, it's not HS10 like in 2019 cd data for which this code was first written")
}

cd_df$HS_CODE <-
  stringr::str_pad(
    string = c(cd_df$HS_CODE),
    side = "left",
    width = 10,
    pad = "0"
  )

# convert from USD to West African Francs 
# using exchange rates from year end
USD_to_FCFA <- tibble(
  YEAR = c(as.character(2024)),       # Keep as numeric (removed as.character)
  EX_RATE = c(633.78)
)

cd_df <- cd_df %>%
  left_join(USD_to_FCFA, by = "YEAR") %>%
  mutate(
    CIF_USD = as.numeric(CIF_USD), 
    CIF_CFA = CIF_USD * EX_RATE    
  ) %>%
  select(-EX_RATE)

rm(USD_to_FCFA)

print(cd_df$CIF_USD)
print(head(cd_df))

# Note that it's CIF and not FOB like in 2019 cd data. 

# Convert dates from string to date format
print(cd_df$DATE)
cd_df$DATE <- as.Date(cd_df$DATE, format = "%d/%m/%Y") # This causes errors due to differences in formatting of dates in original data, but we only need to know it is for year 2024 anyway 
cd_df$YEAR <- as.numeric(2024)
print(cd_df$DATE)

# Convert columns to numeric
cd_df <- cd_df %>%
  mutate(across(c(NET_WEIGHT_KG, CIF_USD, NUMBER_OF_PRODUCTS, GROSS_WEIGHT_KG), as.numeric))

# Translate and standardise units in English
cd_df <- cd_df %>%
  mutate(
    UNIT = case_when(
      # --- TRANSLATIONS AND AGGREGATIONS ---
      
      # 1. Bags (JUTE BAG, SAC, BAG)
      str_detect(toupper(UNIT), "SAC|JUTE|BAG") ~ "JUTE BAG",
      
      # 2. Boxes (CARTON, BOX)
      str_detect(toupper(UNIT), "CARDBOARD|CARTON|BOX") ~ "BOX",
      
      # 3. Bulk Liquid (VRAC, LIQUIDE, FLEXI, CISTERN)
      str_detect(toupper(UNIT), "VRAC, LIQUIDE|FLEXI|CISTERN") ~ "BULK, LIQUID",
      
      # 4. Bulk Solid (VRAC SOLIDE, UNPACKED)
      str_detect(toupper(UNIT), "VRAC SOLIDE|UNPACKED") ~ "BULK SOLID, GRANULAR PARTICLES",
      
      # 5. Parcels (COLIS, PARCEL, PALLET)
      str_detect(toupper(UNIT), "COLIS|PARCEL|PALLET|PALETTES") ~ "PARCEL (PACKAGE)",
      
      # --- CATCH-ALL ---
      # If no rule above matched, keep the original value
      TRUE ~ UNIT 
    )
  )

print(cd_df %>% 
        count(UNIT, sort = TRUE), n=50)

# transformation
# group_by HSCodes
# QA

cd_df <- cd_df %>%
  rename(
    # HS10 = HS_CODE, this needs to be named HS_CODE, for compatibility with fn_trade_data_clean_up later
    # EXPORTER_TAX_ID = EXPORTER_CODE, # this is a naming from process_cote_divoire_2019.R - maybe used in other scripts, but not in this one. 
    COUNTRY_OF_DESTINATION = COUNTRY_OF_DESTINATION,
    # COUNTRY_OF_DESTINATION_2 = PROVENANCE_COUNTRY, # we don't need it since we transfered info from it to the other var. 
    #COUNTRY_OF_ORIGIN = ORIGIN_COUNTRY,
    # CIF_CFA = CIF_VALUE_IN_WEST_AFRICAN_CFA_FRANC, # WE ARE USING FOB VALUES FOR 2023-24 UPDATE
    # CIF_USD = CIF_VALUE_IN_USD
  ) %>%
  mutate(
    HS6 = substr(HS_CODE, 1, 6),
    NET_WEIGHT_TON = NET_WEIGHT_KG/1000,
    GROSS_WEIGHT_TON = GROSS_WEIGHT_KG/1000,
    # CIF_CFA = as.numeric(CIF_CFA), # WE ARE USING CIF VALUES FOR 2023-24 UPDATE
    # CIF_USD = as.numeric(CIF_USD) # WE ARE USING CIF VALUES FOR 2023-24 UPDATE
    #CIF_CFA = as.numeric(CIF_CFA),
    CIF_USD = as.numeric(CIF_USD)
  ) %>%
  select(
    COUNTRY_OF_ORIGIN,
    COUNTRY_OF_DESTINATION,
    YEAR,
    HS6,
    dplyr::everything()
  )

reframe(cd_df, 
        "HS10 in HS6" = unique(HS_CODE_DESCRIPTION), 
        .by = HS6)

# Split commodities
# This step is not necessary because there is only cocoa in the data (unlike in 2019 cd data)

# ... NB we don't export "HS code 1806", i.e. cocoa preparations
# ... after discussion with Javier
# ... there is uncertainty in calculating the % of cocoa, and the volumes is small
# ... it was not purchased anyway, so we don't need to do anything
if(any(grepl("1806", cd_df$HS6))){
  stop("reconsider above comment about HS code 1806: we may need to do something")
}
if(anyNA(cd_df$HS6)){
  stop("not all raws have a HS code, which is not expected")
}


# Fix obvious errors ------------------------------------------------------
summary(cd_df$CIF_CFA)
cd_df %>% filter(CIF_CFA==1) %>% nrow()
cd_df %>% filter(CIF_USD==0) %>% nrow()
cd_df %>% filter(CIF_USD==1) %>% nrow()
cd_df$CIF_CFA %>% unique() %>% sort() %>% head()
cd_df$CIF_USD %>% unique() %>% sort() %>% head()

# 1 and 0 values are strange, but they can be symbolic prices / gifts 
sort(table(cd_df$CIF_CFA), decreasing = TRUE) %>% head()
sort(table(cd_df$CIF_USD), decreasing = TRUE) %>% head()
# Given the proportionality between the five most frequent shipment weights, it looks like they are standard shipments sizes, 
# thus it is normal that they are frequent. 
sort(table(cd_df$NET_WEIGHT_TON), decreasing = TRUE) %>% head()

# As in 2019, 2020 and 2021, there are cases where the value of a shipment was set to 1 CFA (and USD is 0 then)
# ... where 1 West African CFA franc = 0.0019 USD (tiny amounts!)
# We recover it by getting the median price for this HS6 code (per ton) and multiplying by the record's gross weight. 
# There are also several cases where the CIF_CFA == 656
# since they have quite different weights from each others, I consider that the constant 656 is spurious
# and I thus replace it by the weight * median price
cd_df %>% filter(CIF_CFA==1|CIF_CFA==656|CIF_CFA==6560) %>% View()
# sold at a retail price rate of 2 USD / kg. 
cd_df_save <- cd_df
cd_df <- cd_df %>%
  mutate(
    CIF_CFA_PER_TON = CIF_CFA / NET_WEIGHT_TON,
    CIF_USD_PER_TON = CIF_USD / NET_WEIGHT_TON
  ) %>%
  group_by(HS6) %>%
  mutate(
    MED_HS6_CIF_CFA = median(CIF_CFA),
    MED_HS6_CIF_USD = median(CIF_USD),
    MED_HS6_NET_WEIGHT_TON = median(NET_WEIGHT_TON),
    MED_HS6_NET_WEIGHT_TON = median(NET_WEIGHT_TON),
    MED_HS6_CIF_CFA_PER_TON = median(CIF_CFA_PER_TON),
    MED_HS6_CIF_USD_PER_TON = median(CIF_USD_PER_TON)
  ) %>% 
  ungroup() %>% 
  mutate(
    # condition on net weight kg to not be a weird value as well (1 or 0) because then it does not make sense to impute CIF from it
    ERROR = ifelse((CIF_CFA == 1) & NET_WEIGHT_KG > 1, T, F),
    # impute the strange CIF_CFA
    CIF_CFA = case_when(
      ERROR ~ MED_HS6_CIF_CFA_PER_TON * NET_WEIGHT_TON,
      TRUE ~ CIF_CFA
    ),
    # but also the CIF_USD that does not correspond anymore
    CIF_USD = case_when(
      ERROR ~ MED_HS6_CIF_USD_PER_TON * NET_WEIGHT_TON,
      TRUE ~ CIF_USD
    ),
    # we also need to replace the price in these cases (by the median)
    CIF_USD_PER_TON = case_when(
      ERROR ~ MED_HS6_CIF_USD_PER_TON,
      TRUE ~ CIF_USD_PER_TON
    ),
    CIF_CFA_PER_TON = case_when(
      ERROR ~ MED_HS6_CIF_CFA_PER_TON,
      TRUE ~ CIF_CFA_PER_TON
    )
  ) 
# cd_df %>% filter(ERROR) %>% View()

# observe these medians
distinct(cd_df, HS6, .keep_all = T) %>% select(HS6, starts_with("MED_"))
# they are similar to those in 2021. 

# One potential way to investigate outliers further, that was not possible in previous years of custom data for cocoa CIV
# is to divide NET_WEIGHT_KG by NUMBER_OF_PRODUCTS and find outliers in product weight, within UNIT AND HS6 type

#only one instance of this in 2022, with HS code 180200 and would be droped later. 
cd_df %>% filter(CIF_USD == 0) %>% View()
# just drop it now.  
chk <- nrow(cd_df)
# 1. Identify ALL rows that will be dropped by filter(CIF_USD > 0)
#    This includes 0, negative numbers, and NAs.
rows_to_be_dropped <- cd_df %>% 
  filter(CIF_USD <= 0 | is.na(CIF_USD))

# 2. Report what was found BEFORE taking action
print(paste("Found", nrow(rows_to_be_dropped), 
            "rows with CIF_USD <= 0 or NA."))

# 3. Uncomment the line below to manually inspect them
# View(rows_to_be_dropped)

# ---

# 4. Store the starting row count
start_rows <- nrow(cd_df)

# 5. Define exactly how many rows you expect to drop
#    Based on your comment, you expect 2.
expected_to_drop <- 0

# 6. Filter the data
cd_df <- cd_df %>% 
  filter(CIF_USD > 0)

# 7. Calculate how many rows were *actually* dropped
rows_actually_dropped <- start_rows - nrow(cd_df)

# 8. Compare expected vs. actual and stop with a clear message
if (rows_actually_dropped != expected_to_drop) {
  
  # This message is much more informative for debugging
  stop(paste("Row drop mismatch! Expected to drop", expected_to_drop, 
             "row(s), but", rows_actually_dropped, "rows were dropped instead."))
  
} else {
  
  print(paste("Check passed: Successfully dropped", rows_actually_dropped, "row(s)."))
  
}

# 9. Clean up your environment variables
rm(start_rows, rows_actually_dropped, expected_to_drop, rows_to_be_dropped)

# Spot shipments in bag which net weight is not coherent with number of bags and 
# bag cocoa content weight of 65kg (for BEANS, i.e. HS6 == 180100) 
# Note: many bag weights equal or close to 25, all HS6 considered). So this is apparently an actual bag content weight for other products than beans. 
sb <- 
  cd_df %>% 
  filter(UNIT=="SAC EN JUTE"|UNIT=="SAC (SACK)") %>%
  mutate(bag_weight = NET_WEIGHT_KG/NUMBER_OF_PRODUCTS, 
         strange_bags = !(bag_weight<70 & bag_weight>60) & HS6 == 180100) %>% 
  filter(strange_bags) 
# View(sb)
sort(table(sb$bag_weight), decreasing = TRUE) %>% head()
unique(sb$bag_weight)
# so these cases are in two categories: either it's the number of products that is spuriously 1 or 0, in which case we do nothing
# or it's cases where the bag weights are 54, 56 and 86kg, which is not unbelievable so we do nothing either. 



# check whether there are weird values in either currency CIF, based on exchange rate? 
cd_df %>% 
  mutate(EX_RATE = CIF_CFA/CIF_USD) %>% 
  pull(EX_RATE) %>% 
  summary()


# Outliers ----------------------------------------------------
# Here I vizualize outliers and, unlike in 2019, I impute values for some of them
# because they are too large to be left in the data. 

# Outliers:


## Define outliers ---------------------
# Define outliers as values at the 1% and 99% percentiles
# ... which are 2.5x bigger or larger than the upper/lower quartile
my_percentiles <- c(1, 99)
threshold_qr <- 2.5

cd_df <-
  cd_df %>%
  group_by(HS6) %>% # NOTE that we identify outliers within HS6
  mutate(
    QUARTILE_LWR_VOL = summary(NET_WEIGHT_TON)[["1st Qu."]],
    QUARTILE_UPR_VOL = summary(NET_WEIGHT_TON)[["3rd Qu."]],
    QUARTILE_LWR_CIF_USD = summary(CIF_USD)[["1st Qu."]], # do only for USD, since there's no crazy exchange rate
    QUARTILE_UPR_CIF_USD = summary(CIF_USD)[["3rd Qu."]],
    QUARTILE_LWR_FPU = summary(CIF_USD_PER_TON)[["1st Qu."]],
    QUARTILE_UPR_FPU = summary(CIF_USD_PER_TON)[["3rd Qu."]]
  ) %>%
  mutate(
    VOL_OUTLIER = case_when(
      (percent_rank(NET_WEIGHT_TON) < my_percentiles[1] / 100 & NET_WEIGHT_TON < (QUARTILE_LWR_VOL / threshold_qr)) |
        (percent_rank(NET_WEIGHT_TON) > my_percentiles[2] / 100 & NET_WEIGHT_TON > (QUARTILE_UPR_VOL * threshold_qr)) ~ TRUE,
      TRUE ~ FALSE
    ),
    CIF_OUTLIER = case_when(
      (percent_rank(CIF_USD) < my_percentiles[1] / 100 & CIF_USD < (QUARTILE_LWR_CIF_USD / threshold_qr)) |
        (percent_rank(CIF_USD) > my_percentiles[2] / 100 & CIF_USD > (QUARTILE_UPR_CIF_USD * threshold_qr)) ~ TRUE,
      TRUE ~ FALSE
    ),
    FPU_OUTLIER = case_when(
      (percent_rank(CIF_USD_PER_TON) < my_percentiles[1] / 100 & CIF_USD_PER_TON < (QUARTILE_LWR_FPU / threshold_qr)) |
        (percent_rank(CIF_USD_PER_TON) > my_percentiles[2] / 100 & CIF_USD_PER_TON > (QUARTILE_UPR_FPU * threshold_qr)) ~ TRUE,
      TRUE ~ FALSE
    )
  ) %>% # for convenience 
  select(SHPMT_ID, HS6, HS_CODE, HS_CODE_DESCRIPTION, UNIT, NUMBER_OF_PRODUCTS, #QUANTITY, 
         NET_WEIGHT_KG, GROSS_WEIGHT_KG, NET_WEIGHT_TON, GROSS_WEIGHT_TON, CIF_USD, CIF_USD_PER_TON, 
         contains("OUTLIER"), starts_with("MED_"), everything()) %>% 
  arrange(NET_WEIGHT_TON) %>% 
  ungroup()


## Visualize outliers ----------------------

# Volume outliers
# According to boxplot (1.5*IQR)
cd_df %>% 
  ggplot(aes(HS6, NET_WEIGHT_TON)) +
  geom_boxplot() 
# According to present thresholds
cd_df %>% 
  ggplot(aes(HS6, NET_WEIGHT_TON, col = VOL_OUTLIER)) +
  geom_boxplot() 

# CIF 
cd_df %>% 
  ggplot(aes(HS6, CIF_USD)) +
  geom_boxplot() 
# According to present thresholds
cd_df %>% 
  ggplot(aes(HS6, CIF_USD, col = VOL_OUTLIER)) +
  geom_boxplot() 

# ... in price terms
cd_df %>% 
  ggplot(aes(HS6, CIF_USD_PER_TON)) +
  geom_boxplot() 
cd_df %>% 
  ggplot(aes(HS6, CIF_USD_PER_TON, col = FPU_OUTLIER)) +
  geom_boxplot() 

cd_df %>% filter(FPU_OUTLIER) %>% View()
# Look at how many shipments are flagged and whether they are unusually expensive or cheap.

# Inspect volume outliers 
cd_df %>% filter(VOL_OUTLIER) %>% View()
# Check whether the largest shipments are also price outliers. If their value per tonne
# is normal, large volumes are plausible and need no fixing.

# Volume outliers that are also price outliers 
cd_df %>% filter(VOL_OUTLIER & FPU_OUTLIER) %>% View()
# Shipments flagged on both volume and price deserve a closer look.

# Price outliers that are also CIF outliers 
cd_df %>% filter(CIF_OUTLIER & FPU_OUTLIER) %>% View()


# Calculate the % of data identifed as an outlier
# ... using these thresholds
cd_df %>%
  group_by(HS6) %>%
  mutate(
    TOTAL_CIF_USD = sum(CIF_USD),
    TOTAL_VOL = sum(NET_WEIGHT_TON)
  ) %>%
  filter(FPU_OUTLIER) %>%
  summarise(
    PERC_VOL = sum(NET_WEIGHT_TON) / unique(TOTAL_VOL) * 100,
    PERC_CIF_USD = sum(CIF_USD) / unique(TOTAL_CIF_USD) * 100
  )
# If the flagged shipments are a small share of the total (e.g. under 1% per HS code),
# leaving them as they are has little effect on the results.



## Fixing individual outliers (optional) --------------------
# If a few shipments have a value or weight that is clearly wrong (for example a
# misplaced decimal point), fix them here by shipment ID, and write down why.
# Decide which of value or weight is more credible from the number of bags,
# typical shipment sizes for that HS code, and the exporter's usual volumes.
# Example:
# cd_df <- cd_df %>%
#   mutate(NET_WEIGHT_TON = if_else(SHPMT_ID == 123, 250, NET_WEIGHT_TON),
#          CIF_USD_PER_TON = CIF_USD / NET_WEIGHT_TON)


# Export ------------------------------------------------------------------

# Do last check of suitability for upload
cd_df <- prepare_data_for_upload(cd_df) %>%
  select(-CIF_USD_PER_TON, -SHPMT_ID)


# Export

file_name <- input_path("customs", "cocoa_exports_2024.csv")

if(WRITE_OUTPUT){
  message("Writing ", file_name)
  write_delim(cd_df, file_name, delim = ";")
  rm(cd_df, my_percentiles, threshold_qr)
} else {
  message("Switch WRITE_OUTPUT to TRUE if you want the script to write its output")
}


# tidy up
#
