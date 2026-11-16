# Helper functions used by the Côte d'Ivoire input-preparation scripts.

fn_fr_to_en_country_names <- function(col_name){
  case_when(
    col_name == "Arabie Saoudite" ~  "Saoudi Arabia",
    col_name == "Emirats Arabes Unis" ~  "United Arab Emirates",
    col_name == "Etats-Unis" ~  "United States",
    col_name == "Grece" ~  "Greece",
    col_name == "Inde" ~  "India",
    col_name == "Pays-bas" ~  "Netherlands",
    col_name == "Russie, Federation de" ~  "Russia",
    col_name == "Syrienne, Republique arabe" ~  "Syria",
    col_name == "Autre pays" ~  "Unknown",
    TRUE ~ col_name
  )
}

fn_clean_department_names <- function(col_name){
  case_when(
    grepl("ABENGOUROU" , col_name) ~ "ABENGOUROU",
    grepl("AGNIBLEKRO" , col_name) ~ "AGNIBILEKRO",
    grepl("ABOISSO" , col_name) ~ "ABOISSO",
    grepl("AFFERY" , col_name) ~ "AKOUPE", # https://fr.wikipedia.org/wiki/Aff%C3%A9ry
    grepl("BANGOLO" , col_name) ~ "BANGOLO",
    grepl("BONDOUKOU" , col_name) ~ "BONDOUKOU",
    grepl("BOUAFLE" , col_name) ~ "BOUAFLE",
    grepl("DALOA" , col_name) ~ "DALOA",
    grepl("DIVO" , col_name) ~ "DIVO",
    grepl("DUEKOUE" , col_name) ~ "DUEKOUE",
    grepl("GAGNOA" , col_name) ~ "GAGNOA",
    grepl("GUIGLO" , col_name) ~ "GUIGLO",
    grepl("GRAND-LAHOU|GRAND LAHOU" , col_name) ~ "GRAND-LAHOU",
    grepl("GRAND-BASSAM|GRAND BASSAM" , col_name) ~ "GRAND-BASSAM",
    grepl("HERMAKONO|HERMANKONO" , col_name) ~ "DIVO", # https://fr.wikipedia.org/wiki/Hermankono-Di%C3%A8s
    grepl("LAKOTA" , col_name) ~ "LAKOTA",
    grepl("OPOUYO|OUPOUYO|OUPOYO|SOOUBRE" , col_name) ~ "SOUBRE",
    grepl("SEGUELLA|SEGUELA" , col_name) ~ "SEGUELA",
    grepl("SINFRA" , col_name) ~ "SINFRA",
    grepl("TAABO" , col_name) ~ "TAABO",
    grepl("TABOU" , col_name) ~ "TABOU",
    grepl("YAKASSE|ABONGOUA" , col_name) ~ "YAKASSE-ATTOBROU", # https://fr.wikipedia.org/wiki/Abongoua
    
    grepl("SAN-PEDO|SAN PEDRO|GABIADJI|GAGNY" , col_name) ~ "SAN-PEDRO",
    
    TRUE ~ col_name
    
  )
}