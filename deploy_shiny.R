# ==============================================================================
# DEPLOY SHINY APP -> shinyapps.io
# ==============================================================================
# Reads credentials from environment variables and publishes app.R together
# with the CSVs it needs at runtime. Designed to run identically in local
# environments (`Rscript deploy_shiny.R`) and from CI.
#
# Required environment variables:
#   SHINYAPPS_NAME    Account name on shinyapps.io
#   SHINYAPPS_TOKEN   API token (Account -> Tokens -> Show -> Token)
#   SHINYAPPS_SECRET  Secret paired with the token
#
# Optional:
#   SHINYAPPS_APPNAME Public name of the app (default: nih-retractions)
# ==============================================================================

if (!requireNamespace("rsconnect", quietly = TRUE)) {
  install.packages("rsconnect", repos = "https://cloud.r-project.org")
}

acc    <- Sys.getenv("SHINYAPPS_NAME")
tok    <- Sys.getenv("SHINYAPPS_TOKEN")
secret <- Sys.getenv("SHINYAPPS_SECRET")
appnm  <- Sys.getenv("SHINYAPPS_APPNAME", unset = "nih-retractions")

if (acc == "" || tok == "" || secret == "") {
  stop("Missing credentials: set SHINYAPPS_NAME, SHINYAPPS_TOKEN and SHINYAPPS_SECRET.")
}

rsconnect::setAccountInfo(name = acc, token = tok, secret = secret)

# Only the files the app actually reads are uploaded.
# data/raw/ is intentionally excluded (hundreds of MB; regenerable each cron).
files <- c(
  "app.R",
  "data/processed/FINAL_Retractions_Costs_and_Pubs.csv",
  "data/processed/Author_Funding_Matches.csv",
  "data/processed/annual_cpi.csv"
)

missing <- files[!file.exists(files)]
if (length(missing) > 0) {
  stop("Required files not found on disk: ",
       paste(missing, collapse = ", "))
}

cat("Deploying", length(files), "files to shinyapps.io as app:", appnm, "\n")
rsconnect::deployApp(
  appDir         = ".",
  appFiles       = files,
  appPrimaryDoc  = "app.R",
  appName        = appnm,
  account        = acc,
  forceUpdate    = TRUE,
  launch.browser = FALSE
)

cat("Deploy complete.\n")
