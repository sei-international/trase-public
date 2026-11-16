# =============================================================================
# assign departments to licensed cocoa buyers ("acheteurs agréés")
# =============================================================================
# The Conseil du Café-Cacao (CCC) publishes yearly lists of licensed buyers and
# the department they operate in. This script matches the department names to
# the official department codes (LVL_4_CODE), fixing spelling differences by hand.
# It processes the 2018, 2019, 2020 and 2021 lists. The 2024 model uses only
# the 2021 output: licensed_buyers/licensed_buyers_2021.csv (no newer list was found).
# Inputs (public CCC lists, place in <DATA_DIR>/licensed_buyers/):
#   ACHATEURS_AGREES.csv, 2020_ACHATEURS_AGREES.xlsx,
#   ACHETEURS_AGREES_CAMPAGNE_2020_2021.xlsx,
#   PREMIERE_LISTE_ACHETEURS_AGREES_CAMPAGNE_2018_2019.xlsx
# =============================================================================

# Assigning geocodes to Achateurs Agréés (AA)

# Workstation set-up--------------------------------------------------------------------------------------------
library(tidyverse)
library(sf)
library(stringi)
# File paths: see input_preparation/setup.R
source(file.path("input_preparation", "setup.R"))   # also provides str_trans()


# Load licensed-buyer lists----------------------------------------------------------------------------------------
AA_2018 <- read_sf(require_input(input_path("licensed_buyers", "ACHATEURS_AGREES.csv")))
str(AA_2018)
# 2020-09-28:
# it does not retain the column names -> remove first row and rename fields
# dim(AA_2018)
# AA_2018 <- AA_2018[2:325,]
# <- rename(AA_2018,
#       "NOM" = "Field1",
#       "DENOMINATION" = "Field2",
#       "ZONE_DACTIVITE" = "Field3")
# many entries contain a tab (\t), remove this
# AA_2018 <- dplyr::mutate_if(tibble::as_tibble(AA_2018),
#                        is.character,
#                        stringr::str_replace_all, pattern = "\t", replacement = "")
# are they all removed?
# AA_2018 %>%
#  str_extract_all('\t') %>%
#  unlist %>%
#  length
# yes, length = 0
# (2020_ACHATEURS_AGREES.xlsx is the cleaned-up version of the 2020 list)

AA_2020 <- read_sf(require_input(input_path("licensed_buyers", "2020_ACHATEURS_AGREES.xlsx")))
str(AA_2020)
AA_2020 <- rename(AA_2020,
  "NOM" = "NOM & PRENOMS",
  "CODE_DR" = "CODE DR",
  "ZONE_DACTIVITE" = "ZONE D'ACTIVITE"
)

# Load department boundaries------------------------------------------------------------------------
geocodes <- read_sf(require_input(input_path("regions", "departments.geojson")))
str(geocodes)


# remove special characters from AA_2018 and AA_2020----------------------------------------------------
str_trans <- function(x) {
  x %>%
    stri_trans_toupper() %>%
    stri_trans_general("Latin-ASCII")
}
AA_2018 <-
  AA_2018 %>%
  mutate(
    NOM = str_trans(NOM),
    DENOMINATION = str_trans(DENOMINATION),
    ZONE_DACTIVITE = str_trans(ZONE_DACTIVITE)
  )
AA_2020 <-
  AA_2020[1:224, ] %>%
  mutate(
    NOM = str_trans(NOM),
    DENOMINATION = str_trans(DENOMINATION),
    DR = str_trans(DR),
    ZONE_DACTIVITE = str_trans(ZONE_DACTIVITE),
    CONTACT = str_trans(CONTACT),
    TYPE = str_trans(TYPE)
  )


# Linking names of départements to geocodes---------------------------------------------------------------
# département names: AA_2018$ZONE_DACTIVITE & AA_2020$ZONE_DACTIVITE & geocodes$LVL_4_NAME

# problem of spaces in AA_2018$ZONE_DACTIVITE, replace them by "-" as used in geocodes$LVL_4_NAME
AA_2018_geocoded <- AA_2018 %>%
  mutate(
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, " ", "-"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "N'DOUCI", "TIASSALE")
  ) %>%
  left_join(geocodes, by = c("ZONE_DACTIVITE" = "LVL_4_NAME")) %>%
  select(NOM, DENOMINATION, ZONE_DACTIVITE, LVL_4_CODE, geometry)

# for AA_2020
setdiff(AA_2020$ZONE_DACTIVITE, geocodes$LVL_4_NAME)
# "TOULEPLEU"        "YAKASSE ATTOBROU"
AA_2020_geocoded <- AA_2020 %>%
  mutate(
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "TOULEPLEU", "TOULEUPLEU"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "YAKASSE ATTOBROU", "YAKASSE-ATTOBROU")
  ) %>%
  left_join(geocodes, by = c("ZONE_DACTIVITE" = "LVL_4_NAME")) %>%
  select(NOM, DENOMINATION, DR, ZONE_DACTIVITE, CODE, CONTACT, TYPE, LVL_4_CODE, geometry)



# Save---------------------------------------------------------------
write_delim(AA_2018_geocoded, input_path("licensed_buyers", "ACHATEURS_AGREES_2018_GEOCODED.csv"), delim = ";")
write_delim(AA_2020_geocoded, input_path("licensed_buyers", "ACHATEURS_AGREES_2020_GEOCODED.csv"), delim = ";")

# do the same for the 2020-2021 file-------------------------------------------------------------------
AA_2021 <- read_sf(require_input(input_path("licensed_buyers", "ACHETEURS_AGREES_CAMPAGNE_2020_2021.xlsx"))) %>%
  select(-"NÂ°") %>%
  rename(
    "NOM" = "REPRESENTANT",
    "ZONE_DACTIVITE" = "DEPARTEMENT"
  ) %>%
  mutate(
    NOM = str_trans(NOM),
    DENOMINATION = str_trans(DENOMINATION),
    ZONE_DACTIVITE = str_trans(ZONE_DACTIVITE)
  )
setdiff(AA_2021$ZONE_DACTIVITE, geocodes$LVL_4_NAME)
# "TOULEPLEU" "GRAND-BEREBY" "ICAN I" "BIANKOTJ MA"
# correct spelling (i.e. as in geocodes) =
# "TOULEUPLEU" - - "BIANKOUMA"
# conversion mistake with "ICAN I" representing "KANI" in pdf
# GRAND-BEREBY is part of the San Pedro department according to Wikipedia
AA_2021_geocoded <- AA_2021 %>%
  mutate(
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "TOULEPLEU", "TOULEUPLEU"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "GRAND-BEREBY", "SAN-PEDRO"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "ICAN I", "KANI"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "BIANKOTJ MA", "BIANKOUMA")
  ) %>%
  left_join(geocodes, by = c("ZONE_DACTIVITE" = "LVL_4_NAME")) %>%
  select(NOM, DENOMINATION, ZONE_DACTIVITE, LVL_4_CODE, geometry)
# save
write_delim(AA_2021_geocoded, input_path("licensed_buyers", "licensed_buyers_2021.csv"), delim = ";")

# SAME FOR THE 2018-2019 FILE----------------------------------------------------------------------------
AA_2019 <- read_sf(require_input(input_path("licensed_buyers", "PREMIERE_LISTE_ACHETEURS_AGREES_CAMPAGNE_2018_2019.xlsx"))) %>%
  select(-"NÂ°", -Field5, -Field6) %>%
  rename(
    "NOM" = "NOM & PRENOMS",
    "ZONE_DACTIVITE" = "ZONE D'ACTIVITE"
  ) %>%
  filter(!is.na(NOM)) %>%
  mutate(
    NOM = str_trans(NOM),
    DENOMINATION = str_trans(DENOMINATION),
    ZONE_DACTIVITE = str_trans(ZONE_DACTIVITE)
  )
setdiff(AA_2019$ZONE_DACTIVITE, geocodes$LVL_4_NAME)
# [1] "SAN PEDRO"        "YAKASSE ATTOBROU" "ARRAN"            "M BATTO"          "BIANKOUMAN"
# [6] "BUY()"            "GRAND LAHOU"      "N DOUCI"          "SASSAN D RA"      "KOUN FAO"
AA_2019_geocoded <- AA_2019 %>%
  mutate(
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "SAN PEDRO", "SAN-PEDRO"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "YAKASSE ATTOBROU", "YAKASSE-ATTOBROU"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "ARRAN", "ARRAH"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "M BATTO", "M'BATTO"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "BIANKOUMAN", "BIANKOUMA"),
    ZONE_DACTIVITE = gsub("BUY()", "BUYO", ZONE_DACTIVITE, fixed = TRUE),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "GRAND LAHOU", "GRAND-LAHOU"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "N DOUCI", "TIASSALE"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "SASSAN D RA", "SASSANDRA"),
    ZONE_DACTIVITE = str_replace(ZONE_DACTIVITE, "KOUN FAO", "KOUN-FAO")
  ) %>%
  left_join(geocodes, by = c("ZONE_DACTIVITE" = "LVL_4_NAME")) %>%
  select(NOM, DENOMINATION, ZONE_DACTIVITE, LVL_4_CODE, geometry)
# save
write_delim(AA_2019_geocoded, input_path("licensed_buyers", "ACHATEURS_AGREES_2019_GEOCODED.csv"), delim = ";")
