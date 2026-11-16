# =============================================================================
# test_buyer_names.R: supplier-link company names are cleaned like customs
# names, combined buyers are split, and duplicate links are merged
# (standardise_buyer_names in model/R/prepare_inputs.R).
# Run from the toolkit's top folder:  Rscript tests/test_buyer_names.R
# =============================================================================
suppressMessages(library(dplyr))
TOOLKIT_ROOT <- normalizePath(getwd())
source(file.path(TOOLKIT_ROOT, "model", "load.R"))
rules <- read_name_rules(file.path(TOOLKIT_ROOT, "countries", "cote_divoire", "rules", "company_group_rules.csv"))

check <- function(ok, what) { cat(if (isTRUE(ok)) "PASS " else "FAIL ", what, "\n"); if (!isTRUE(ok)) quit(status = 1) }

links <- tribble(
  ~SUPPLIER_ID, ~BUYER,                             ~TRADER_NAME,                       ~NUM_FARMERS, ~FLOW_ID,
  "S1",         "OFI",                              "OFI",                              100L,         "f1",
  "S1",         "BARRY CALLEBAUT + CARGILL + OLAM", "BARRY CALLEBAUT + CARGILL + OLAM", 700L,         "f2",
  "S2",         "ETG",                              "ETG",                              NA,           "f3",
  "S2",         "Etc Group",                        "Etc Group",                        50L,          "f4",
  "S3",         "HERSHEY + BLOMMER",                NA,                                 300L,         "f5",
  "S4",         NA,                                 NA,                                 NA,           "f6",
  "S4",         NA,                                 NA,                                 NA,           "f7",
  "S5",         "CARGILL",                          "CARGILL",                          80L,          "f8"
)
out <- standardise_buyer_names(links, rules)

s1 <- out %>% filter(SUPPLIER_ID == "S1") %>% arrange(BUYER)
check(identical(s1$BUYER, c("BARRY CALLEBAUT", "CARGILL", "OLAM")), "OFI is grouped as OLAM; combined buyer split into three")
check(s1$NUM_FARMERS[s1$BUYER == "OLAM"] == 100L, "the link disclosed on its own is kept over the one split from a combined name")
check(all(s1$NUM_FARMERS[s1$BUYER != "OLAM"] == 700L), "split links keep the link's farmer number")
check(identical(s1$TRADER_NAME, s1$BUYER), "split links of a trader are traders")
check(!any(duplicated(out$FLOW_ID)), "FLOW_IDs stay unique")
s2 <- out %>% filter(SUPPLIER_ID == "S2")
check(nrow(s2) == 1 && s2$BUYER == "ETC GROUP" && s2$NUM_FARMERS == 50L, "ETG and Etc Group merged, keeping the link with a farmer number")
s3 <- out %>% filter(SUPPLIER_ID == "S3")
check(identical(sort(s3$BUYER), c("BLOMMER", "HERSHEY")) && all(is.na(s3$TRADER_NAME)), "non-trader combined buyers split, still not traders")
check(sum(out$SUPPLIER_ID == "S4") == 2, "links without a buyer are left alone")
check(identical(unlist(out[out$SUPPLIER_ID == "S5", c("BUYER", "TRADER_NAME")], use.names = FALSE), c("CARGILL", "CARGILL")), "clean names unchanged")
