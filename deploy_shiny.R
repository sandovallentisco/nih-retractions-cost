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

# Disable renv's strict snapshot validation: the binary install of tidyverse
# from PPM occasionally leaves transitive deps like cpp11 or progress missing
# as standalone packages, which would otherwise abort the snapshot.
Sys.setenv(RENV_CONFIG_VALIDATE = "FALSE")

# Force rsconnect to bake CRAN URLs into the deployment manifest. PPM stamps
# the Repository field of installed packages with the literal "RSPM", which
# shinyapps.io's build server cannot resolve.
options(repos = c(CRAN = "https://cloud.r-project.org"))

# Re-install packages whose RSPM Repository field has caused shinyapps.io
# build failures. Reinstalling from CRAN updates each package's DESCRIPTION
# to Repository="CRAN", so the manifest URLs become resolvable absolute
# CRAN paths. Extend this list if new packages surface in build logs.
pkgs_to_reinstall_from_cran <- c("isoband")
for (p in pkgs_to_reinstall_from_cran) {
  if (p %in% rownames(installed.packages())) {
    cat("[deploy] Reinstalling", p, "from CRAN to fix PPM URL scheme...\n")
    suppressWarnings(remove.packages(p))
  }
  install.packages(p, repos = "https://cloud.r-project.org",
                   quiet = TRUE, dependencies = FALSE)
}

acc    <- Sys.getenv("SHINYAPPS_NAME")
tok    <- Sys.getenv("SHINYAPPS_TOKEN")
secret <- Sys.getenv("SHINYAPPS_SECRET")
appnm  <- Sys.getenv("SHINYAPPS_APPNAME")

# Sys.getenv's `unset` default only kicks in when the variable is *unset*.
# In CI the workflow always passes SHINYAPPS_APPNAME (potentially as an empty
# string when the secret has not been configured), so we apply the fallback
# explicitly here.
if (nchar(appnm) == 0) {
  appnm <- "nih-retractions"
}

# Sanity-check the app name: shinyapps.io requires >=4 characters, only
# letters, numbers, dashes and hyphens. Replace invalid characters with
# a dash and pad with a suffix if needed.
appnm <- gsub("[^A-Za-z0-9-]", "-", appnm)
if (nchar(appnm) < 4) {
  appnm <- paste0(appnm, "-app")
}

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

# shinyapps.io's API gateway occasionally returns transient 502 / 503 errors
# while rsconnect polls the deployment task. Wrap deployApp in a retry loop
# so a network blip does not turn a real success into a workflow failure.
deploy_attempt <- function() {
  rsconnect::deployApp(
    appDir         = ".",
    appFiles       = files,
    appPrimaryDoc  = "app.R",
    appName        = appnm,
    account        = acc,
    forceUpdate    = TRUE,
    launch.browser = FALSE
  )
}

max_attempts <- 3
for (attempt in seq_len(max_attempts)) {
  result <- tryCatch(
    {
      deploy_attempt()
      list(ok = TRUE, error = NULL)
    },
    error = function(e) list(ok = FALSE, error = e)
  )
  if (isTRUE(result$ok)) {
    cat("Deploy complete.\n")
    quit(status = 0)
  }

  msg <- conditionMessage(result$error)
  cat(sprintf("Attempt %d/%d failed: %s\n", attempt, max_attempts, msg))

  is_transient <- grepl("50[023]|gateway|timeout|connection",
                        msg, ignore.case = TRUE)
  if (!is_transient || attempt == max_attempts) {
    stop(result$error)
  }
  cat("Transient error detected; sleeping 30s before retry...\n")
  Sys.sleep(30)
}
