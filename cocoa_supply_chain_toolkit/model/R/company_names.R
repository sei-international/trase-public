# =============================================================================
# company_names.R: cleaning and grouping company names
# =============================================================================
# Customs records spell the same company in many ways ("CARGILL WEST AFRICA",
# "CARGIL COCOA", ...). The model needs one name per company GROUP so that
# shipments can be matched to the companies that disclose their suppliers.
#
# Name mapping is driven by RULE TABLES (CSV files, one per country), not by
# code. A rule table has columns:
#   order    rules are tried in this order; the FIRST matching rule wins
#   pattern  a regular expression (R/POSIX extended syntax, as in grepl())
#   value    the name to return when the pattern matches
#   comment  free text, for the analyst
# Names that match no rule are returned unchanged.
#
# Two rule tables are used per country:
#   company_group_rules.csv    customs name -> company group (e.g. "CARGILL")
#   exporting_cooperative_rules.csv  customs name -> "<ACRONYM> (COOPERATIVE)" for
#                             cooperatives that export directly
# =============================================================================

#' Upper-case and strip accents (e.g. "Société" -> "SOCIETE").
str_trans <- function(x) {
  x %>%
    stringi::stri_trans_toupper() %>%
    stringi::stri_trans_general("Latin-ASCII")
}

#' Remove dots and common legal-form suffixes (LTD, SAS, GMBH, ...).
clean_corp_acronyms <- function(col_name) {
  stringr::str_squish(
    gsub("[.]| SL$| LTD$| CO$| LLC| INC| AS$| SRL$| BV$| SAS$| GMBH$|OOO LIMITED$| -SA$| (SAS)$| S.A.$| S.A.S$| - S.A.S$|-SA$|(SA)$", "", col_name)
  )
}

#' Read a rule table (see header of this file).
read_name_rules <- function(path) {
  rules <- readr::read_delim(path, delim = ";", show_col_types = FALSE,
                             col_types = readr::cols(order = "i", .default = "c"),
                             locale = readr::locale(encoding = "UTF-8"))
  stopifnot(all(c("order", "pattern", "value") %in% names(rules)))
  rules[order(rules$order), ]
}

#' Apply a rule table to a character vector: first matching rule wins,
#' unmatched names are returned unchanged.
apply_name_rules <- function(x, rules) {
  result <- x
  matched <- rep(FALSE, length(x))
  for (i in seq_len(nrow(rules))) {
    hit <- !matched & grepl(rules$pattern[i], x)
    result[hit] <- rules$value[i]
    matched <- matched | hit
  }
  result
}

#' Company group of a name: the cleaning used for exporters, importers AND
#' the companies in the supplier links, so that both sides of the match use
#' the same names (e.g. "Cargill West Africa" and "CARGIL" -> "CARGILL").
company_group <- function(x, group_rules) {
  apply_name_rules(clean_corp_acronyms(str_trans(x)), group_rules)
}

#' Add cleaned and grouped names for exporters and importers to trade data.
#'
#' Produces:
#'   EXPORTER_ORIGINAL / IMPORTER_ORIGINAL   names as in customs
#'   EXPORTER_CLEAN                          cleaned exporter name
#'   EXPORTER_GROUP_CLEAN / IMPORTER_GROUP_CLEAN  company group, or
#'                                           "<ACRONYM> (COOPERATIVE)"
clean_trade_names <- function(trade, config) {
  group_rules <- config$rules$company_groups
  coop_rules  <- config$rules$exporting_cooperatives
  trade %>%
    rename(EXPORTER_ORIGINAL = EXPORTER,
           IMPORTER_ORIGINAL = IMPORTER) %>%
    mutate(
      # exporting cooperatives first
      EXPORTER_CLEAN = apply_name_rules(clean_corp_acronyms(str_trans(EXPORTER_ORIGINAL)), coop_rules),

      EXPORTER_GROUP_CLEAN = company_group(EXPORTER_ORIGINAL, group_rules),
      EXPORTER_GROUP_CLEAN = apply_name_rules(str_trans(EXPORTER_GROUP_CLEAN), coop_rules),

      IMPORTER_GROUP_CLEAN = company_group(IMPORTER_ORIGINAL, group_rules),
      IMPORTER_GROUP_CLEAN = apply_name_rules(str_trans(IMPORTER_GROUP_CLEAN), coop_rules)
    )
}
