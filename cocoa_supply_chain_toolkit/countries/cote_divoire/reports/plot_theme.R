# Trase plotting colours and ggplot theme, used by the QA report.
# Used only by the optional quality-check report. load_trase_fonts() needs the Trase brand fonts and is not called.

#######################
## Trase Fonts
#######################

#' @export
.trase_title_font <- "Merriweather Light"

#' @export
.trase_label_font <- "DecimaMonoPro"



#' @title Load Trase Fonts
#'
#' Load Trase fonts into R. Gives a warning if they can't be loaded correctly.
#' NOTE: Running this script requires prior installation of the Trase fonts
#' on your machine. If they are not installed, R's default fonts are used.
#'
#' # Visual Guides:
#' Titles in Merriweather Light
#' Values, data, tags, legends in Decima Mono Pro
#' @export

load_trase_fonts <- function() {
  are_both_trase_fonts_installed <-
    (.trase_title_font %in% extrafont::fonts()) ||
      (.trase_label_font %in% extrafont::fonts())

  if (are_both_trase_fonts_installed) {
    return()
  }

  if (Sys.info()[["sysname"]] == "Windows") {
    tryCatch(
      windowsFonts(DecimaMonoPro = windowsFont("DecimaMonoPro")),
      windowsFonts(Merriweather = windowsFont("Merriweather Light")),
      error = function(e) warning("Unable to load all Trase fonts, are they installed on your computer?\n", paste0(e))
    )
  } else {
    tryCatch(
      extrafont::font_import(pattern = "Decima", prompt = FALSE),
      extrafont::font_import(pattern = "Merriweather", prompt = FALSE),
      error = function(e) warning("Unable to load all Trase fonts, are they installed on your computer?\n", paste0(e))
    )

    extrafont::loadfonts()
  }
}
## TODO: Add better error messages if fonts not installed on machine or not found in R
## TODO: If Decima can not be installed the alternate typeface of Decima Mono is Courier.
## TODO: the alternate typeface of Merriweather is Georgia



###############################
## Trase Color Palettes
################################

#' Trase Color Palettes
#'
#' A list of color palettes based on Trase visual guidelines
#' Stylizes graphs and charts in Trase's ggplot theme and can be used ad-hoc
#'
#' @keywords plot, ggplot, visual, color, palettes
#' @export
#' @examples
#' trase_palettes[["linear"]]
#' trase_palettes[["categorical"]]
trase_palettes <- list()

# Palettes from Trase visual guidelines as of 2019-06-28
trase_palettes[["linear"]] <-
  c(
    "#FEDFE2", "#FCBFC5", "#FB9EA8", "#FA7E8B", "#F85E6E",
    "#CF5867", "#A85360", "#6F4C55", "#47474F"
  )

trase_palettes[["categorical"]] <-
  c(
    "#F3CF19", "#6BE4CC", "#639DE6", "#8C63E6", "#E763DF", "#F85E6E",
    "#C08A5E", "#F8D7B1", "#706C61", "#458082", "#FB9EE0", "#CEA532",
    "#9ED679", "#436CED", "#CEA5E0", "#FFE76B", "#DEBC8B", "#D7F2BA",
    "#4B7F52", "#885053"
  )

trase_palettes[["grey"]] <- c("#ECECEC", "#E2E3E4", "#838B8F", "#37444B")
trase_palettes[["green"]] <- c(
  "#FFF0C2", "#9ED679", "#5EB920",
  "#4D8930", "#374F47"
)
main_chart_line <- trase_palettes[["grey"]][4]

# added 2019-12
trase_palettes[["divergent"]] <- c(
  "#5EB920", "#9ED679", "#FFF0C2",
  "#FB9EA8", "#F85E6E"
)

# Colours for map specifications
trase_map_border <- trase_palettes[["grey"]][4]
trase_country_background <- trase_palettes[["grey"]][1]

## Additional Trase 2024 colours
trase_palettes[["TraseGreen_TraseGray_TraseRed"]] <- c("#BBFFEC", "#19404C", "#FF6A5F")
trase_palettes[["no_data"]] <- "#E2EAE7"
trase_palettes[["y_axis"]] <- "#839A8C"
trase_palettes[["x_axis"]] <- "#798B85"
trase_palettes[["legend"]] <- "#4D655E"
trase_palettes[["title"]] <- "#31464E"

trase_palettes[["negative"]] <- c("#FFF1C3", "#FCD295", "#FAB46A", "#F88561", "#E07571", "#E9585A", "#D62931", "#B9383D", "#9C3A3D")
trase_palettes[["positive"]] <- c("#F7F3E8", "#EBCFEA", "#DEAAEB", "#D185EC", "#AA7FF5", "#8B85FF", "#6B73E0", "#4B5FC2", "#2A4AA4")
trase_palettes[["commodities"]] <- c("#E4FDF6", "#A6E6D7", "#92CEC3", "#7EB6AF", "#6A9F9B", "#568787", "#427074", "#2D5860", "#19404C")
trase_palettes[["spike"]] <- c("#FFF1C3", "#FCD295", "#FAB46A", "#F88561", "#E07571", "#E9585A", "#D62931", "#B9383D", "#9C3A3D", "#421D23")
trase_palettes[["divergent"]] <- c("#F45C57", "#F79069", "#FABF88", "#FCE1B3", "#FAEED3", "#EFDCE5", "#D9B0EB", "#B38FEE", "#8180F2")
trase_palettes[["graph_red"]] <- c("#F6EFED", "#F9C2BD", "#FB968E", "#FF7E75", "#F7564B", "#E15E56", "#BB4F4A", "#863939", "#421D23")
trase_palettes[["graph_bluegreen"]] <- c("#BAFFEB", "#A6E6D7", "#92CEC3", "#7EB6AF", "#6A9F9B", "#568787", "#427074", "#2D5860", "#19404C")
trase_palettes[["graph_bubble"]] <- c("#E17227", "#4E6356", "#808883", "#9DC3B7", "#BBFFEC", "#DCB3A4", "#FF6A5F", "#F3AC2F", "#E9EF00")


#' Spread color palette
#'
#' When dealing with a linear color palette with many intervals but few
#' categories to visualize, this function "spreads" the palette so that
#' colors are equally spaced throughout the palette, remain relatively close
#' to the center of the linear palette, and maintain
#' as much distinction as possible
#'
#' @param pal a color palette, as a vector of color codes
#' @param len_out the number of output colors you want
#' @keywords trase, visual, palette
#' @export
#' @examples
#' spread_palette(c("#AAAAAA", "#BBBBBB", "#CCCCCC", "#DDDDDD", "#EEEEEE"), 3)
spread_palette <- function(pal, len_out) {

  # if just one option, use the middle-ground color
  if (len_out == 1) {
    return(pal[round(length(pal) / 2)])
  }

  # if less than 3 options, compress palette a bit (works better
  # with Trase linear palettes)
  if (len_out <= 3) {
    palette_locations <-
      as.integer(seq(length(pal) / 4, 3 * length(pal) / 4, length.out = len_out))
    return(pal[palette_locations])
  }

  # for all else spread evenly amongst whole palette
  palette_locations <- as.integer(seq(1, length(pal), length.out = len_out))


  pal[palette_locations]
}

#########################
## Style and formatting
#########################

.format_trase_numeric_single <- function(number) {
  # handle NAs and NULLs
  if (is.na(number) || is.null(number) || number == 0) {
    return(number)
  }

  # if number is divisible by 1 trillion
  if ((abs(number) %% 1e12) == 0) {
    number_as_billion <- paste0((number / 1e12), "T")
    return(number_as_billion)
  } # if number is divisible by 1 billion, or over 1 billion and divisible by 50 million
  if (abs(number) %% 1e9 == 0 || ((abs(number) %% 5e7 == 0) && (abs(number) > 1e9))) {
    number_as_billion <- paste0((number / 1e9), "B")
    return(number_as_billion)
  } # if number is divisible by 1 million, or over 1 million and divisible by 50 thousand
  if (abs(number) %% 1e6 == 0 || ((abs(number) %% 5e4 == 0) && (abs(number) > 1e6))) {
    number_as_million <- paste0((number / 1e6), "M")
    return(number_as_million)
  } # if number is divisible by 1 thousand, or over 1 thousand and divisible by 50
  if (abs(number) %% 1e3 == 0 || ((abs(number) %% 50 == 0) && (abs(number) > 1e3))) {
    number_as_thousand <- paste0((number / 1e3), "K")
    return(number_as_thousand)
  }

  # if nothing else, format as comma
  return(scales::comma(number))
}

#' Format Trase Numeric
#'
#' Takes in a number, returns the number formatted according to Trase Visual Guidlines for plotting
#'
#' @param num_list a number, or iterable of numbers
#' @keywords visuals, plotting, number
#' @export
#' @examples
#' format_trase_numeric(400000)
#' format_trase_numeric(c(10000, 500000000, 987451, 50))
format_trase_numeric <- function(num_list) {
  sapply(num_list, FUN = .format_trase_numeric_single)
}

##########################
## Trase ggplot theme
##########################


#' Trase ggplot theme
#'
#' Stylizes graphs and charts to more closely align with Trase visual guidelines
#'
#' @keywords plot, ggplot
#' @export

theme_trase <- function() {
  ggplot2::theme_minimal() +
    ggplot2::theme(
      panel.grid = ggplot2::element_line(color = trase_palettes[["grey"]][2]),
      panel.grid.minor = ggplot2::element_blank(),
      panel.grid.major.x = ggplot2::element_blank(),
      panel.grid.minor.x = ggplot2::element_blank(),
      legend.text = ggplot2::element_text(
        color = trase_palettes[["grey"]][4],
        family = .trase_label_font
      ),
      axis.text = ggplot2::element_text(color = trase_palettes[["grey"]][3]),
      axis.line.x = ggplot2::element_line(color = trase_palettes[["grey"]][4]),
      axis.line.y = ggplot2::element_blank(),
      axis.title.y = ggplot2::element_text(angle = 0, vjust = .5),
      plot.title = ggplot2::element_text(family = .trase_title_font),
      plot.subtitle = ggplot2::element_text(
        color = trase_palettes[["grey"]][3],
        family = .trase_title_font
      ),
      text = ggplot2::element_text(family = .trase_label_font, size = 13)
    )
}
