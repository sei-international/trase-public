# Checks that a prepared input table is clean before it is saved
# ... Ensures the data meet requirements specified:

fn_check_for_scientific_notation <- function(x) {
  any(map_lgl(x, ~ grepl("[[:digit:]]e[[:digit:]]", .x)))
}

rm_problem_characters <- function(x) {
  gsub(';|\r|\t|\n|"', "", x)
}

prepare_data_for_upload <- function(df) {
  # Ensures the data meet requirements specified:
  # [1] All information cast to character
  # [2] no scientific notation
  # [3] no stray ";", end-of-line characters, or " inside fields
  # [4] Encoding is utf-8
  # [5] All HS codes have 6 digits, considering leading zeros
  # [6] Replace NA cell by empty cells ("")

  # [1] All columns cast to character
  options(scipen = 999)
  df <- df %>% mutate_all(as.character)
  message("All columns now as.character")

  # [2] Check no scientific notation
  if (any(map_lgl(df, fn_check_for_scientific_notation))) {
    stop("Scientific notation still present - TobyR will be peeved")
  } else {
    message("No scientific notation detected - Pass")
  }

  # [3] Remove stray ";",  end of line characters, or apostrophe '"'
  df <- df %>%
    mutate_if(is.character, rm_problem_characters)
  if (any(map_lgl(df, ~ any(grepl(';|\r|\t|\n|"', .x))))) {
    stop("Problem characters remain")
  } else {
    message("No problem characters")
  }

  # [4] Encoding is utf-8
  # ... I accept 'unknown' as UTF-8, since I've never run into an issue with 'unknown' previously
  my_encodings <-
    map(df, ~ unique(Encoding(.x))) %>%
    unlist() %>%
    unique()
  if (any(map_lgl(my_encodings, ~ .x %in% c("unknown", "UTF-8")) == FALSE)) {
    stop("Correct encoding before preceding")
  } else {
    message("Encodings look OK")
  }


  # [5] All HS codes have 6 digits, considering leading zeros
  if (!("HS6" %in% colnames(df))) {
    stop("Need an HS6 column")
  }
  num_characters <-
    df %>%
    mutate(NCHAR = nchar(HS6)) %>%
    pull(NCHAR) %>%
    unique()
  if (!(length(num_characters) == 1 & num_characters == "6")) {
    df <-
      df %>%
      mutate(HS6 = str_pad(HS6, side = "left", pad = "0", width = 6))
    num_characters <-
      df %>%
      mutate(NCHAR = nchar(HS6)) %>%
      pull(NCHAR) %>%
      unique()
  }
  if (!(length(num_characters) == 1 & num_characters == "6")) {
    stop("Some HS6 codes with more than six characters")
  } else {
    message("HS6 codes look OK")
  }

  # [6] Replace NA cell by empty cells ("")
  df[is.na(df)] <- ""

  # Exit
  return(df)
}
