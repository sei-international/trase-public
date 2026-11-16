# Install the R packages the toolkit needs. Run once:  Rscript install_packages.R
# 'sf' reads map files; on Linux it needs the GDAL, GEOS and PROJ system
# libraries first (see https://r-spatial.github.io/sf/#installing).
needed <- c(
  # the model
  "dplyr", "tidyr", "purrr", "stringr", "readr", "tibble", "sf", "readxl",
  # the input-preparation examples
  "tidyverse", "countrycode",
  # the tests
  "writexl",
  # the optional quality-check report
  "rmarkdown", "knitr", "kableExtra", "tidyverse", "viridis", "scales", "ggpubr"
)
missing <- setdiff(needed, rownames(installed.packages()))
if (length(missing) > 0) install.packages(missing, repos = "https://cloud.r-project.org")
message("All packages installed: ", all(needed %in% rownames(installed.packages())))
