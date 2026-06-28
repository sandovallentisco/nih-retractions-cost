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

# rsconnect determines the source URL for each package by reading the
# Repository field of its DESCRIPTION file. Posit Public Package Manager
# stamps that field with the literal "RSPM"; shinyapps.io's build server
# cannot resolve URLs of the form "RSPM/src/contrib/<pkg>.tar.gz" and aborts
# image creation. Re-stamping every installed package's DESCRIPTION to
# Repository="CRAN" makes the resulting manifest point at fully qualified
# CRAN URLs, which shinyapps.io resolves correctly. The Repository field is
# pure metadata, so this rewrite is harmless to the runtime behaviour.
restamp_repository_field <- function() {
  patched <- 0
  cran_url <- "https://cloud.r-project.org"
  for (lib in .libPaths()) {
    if (!dir.exists(lib)) next
    # Skip the system R library (e.g. /opt/R/.../library) which holds base
    # and recommended packages like ``boot`` and ``MASS``. They are shipped
    # with R itself, are read-only for the running user, and shinyapps.io
    # already has them, so they do not need re-stamping.
    if (file.access(lib, mode = 2) != 0) next
    for (pkg_dir in list.dirs(lib, recursive = FALSE)) {
      desc_file <- file.path(pkg_dir, "DESCRIPTION")
      if (!file.exists(desc_file)) next
      if (file.access(desc_file, mode = 2) != 0) next
      lines <- readLines(desc_file, warn = FALSE)
      # Match RSPM (PPM stamps), CRAN (regular install), or any leftover
      # alias and replace with the full CRAN URL. shinyapps.io concatenates
      # this value with "/src/contrib/<pkg>_<ver>.tar.gz" to fetch the
      # source, so it must be a fully qualified URL, not a short alias.
      idx <- grep("^Repository:\\s*(RSPM|CRAN)\\s*$", lines)
      if (length(idx) == 0) next
      lines[idx] <- paste0("Repository: ", cran_url)
      tryCatch(
        writeLines(lines, desc_file),
        error = function(e) {
          cat("[deploy]   skip", basename(pkg_dir),
              "(not writable):", conditionMessage(e), "\n")
        }
      )
      patched <- patched + 1
    }
  }
  cat("[deploy] Re-stamped Repository field on", patched, "packages.\n")
}
restamp_repository_field()

acc    <- trimws(Sys.getenv("SHINYAPPS_NAME"))
tok    <- trimws(Sys.getenv("SHINYAPPS_TOKEN"))
secret <- trimws(Sys.getenv("SHINYAPPS_SECRET"))
appnm  <- trimws(Sys.getenv("SHINYAPPS_APPNAME"))

# Print credential diagnostics (lengths only; never the values themselves).
# This catches silent issues such as a secret pasted with a trailing newline
# or a regenerated token never updated in GitHub Secrets. Expected sizes:
#   name   ~ 25 chars  (e.g. "z8abx8-alejandro-sandoval")
#   token  = 32 hex chars
#   secret ~ 76 base64 chars
cat("[deploy] Credential lengths:",
    "name=", nchar(acc),
    "token=", nchar(tok),
    "secret=", nchar(secret),
    "appname=", nchar(appnm),
    "\n")

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
  "data/processed/annual_cpi.csv",
  "data/processed/author_grant_keep.csv"
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
