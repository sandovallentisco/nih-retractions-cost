# =============================================================================
# build_collision_flags.R
# -----------------------------------------------------------------------------
# Provenance for the name-collision artefacts used by the consequences analysis
# (Figure 1 of policy_analysis.qmd and the sensitivity table in the Supplement):
#   data/processed/author_collision_flags.csv   (author level)
#   data/processed/author_grant_keep.csv         (grant level, used as the MAIN filter)
#
# Common author names (e.g. "Wei Li", "Wei Chen") can match the NIH grant history
# of several DIFFERENT investigators who share that name. When that happens, the
# funding attributed to a retracted author blends two or more people, which inflates
# and stabilises the per-author funding trajectories (collision authors carry large,
# pooled portfolios that rarely fall to zero).
#
# We use the NIH ExPORTER project files, in which every project lists the unique
# person identifiers (PI_IDS) and awardee institution (ORG_NAME) of its PI(s).
#   - A retracted-author name that maps to >1 distinct PI_ID is a "collision".
#   - For a collision, we identify the REAL person's PI_ID(s) as those holding at
#     least one grant whose awardee institution matches the institution on the
#     retracted paper, then keep only the grants belonging to that PI_ID. Because
#     PI_ID is stable when a researcher changes institution, this isolates the real
#     person's full trajectory (including post-move grants) while dropping the grants
#     of same-named others. Non-collision authors keep all of their grants.
#   - A collision author with NO institution-matching grant has no identifiable real
#     PI_ID; all of their grants are dropped (they leave the cohort).
#
# Outputs (relative to repo root):
#   author_collision_flags.csv
#     Original_Author_Name, n_pi_id, n_grant_orgs, aff_match, exclude_consequences
#       (author-level; exclude_consequences = collision with no institution match.
#        Retained for reporting and the author-level sensitivity row.)
#   author_grant_keep.csv
#     Original_Author_Name, Grant_ID, is_collision, keep_consequences
#       (grant-level; the MAIN filter applied to the funding rows.)
#
# Inputs:
#   data/raw/nih_reporter/RePORTER_PRJ_C_FY*.csv   (CORE_PROJECT_NUM, PI_NAMEs, PI_IDS, ORG_NAME)
#   data/processed/Author_Funding_Matches.csv      (retracted author -> grant/PI)
#   data/processed/FINAL_Retractions_Costs_and_Pubs.csv  (Record ID -> Institution)
#
# Run once from the repo root:  Rscript build_collision_flags.R
# =============================================================================
suppressMessages({library(tidyverse); library(data.table)})

raw_dir      <- "data/raw/nih_reporter"
au_file      <- "data/processed/Author_Funding_Matches.csv"
pap_file     <- "data/processed/FINAL_Retractions_Costs_and_Pubs.csv"
flags_file   <- "data/processed/author_collision_flags.csv"
keep_file    <- "data/processed/author_grant_keep.csv"

# Normalise a PI name to a comparable key: upper-case, then drop dots and the "(contact)"
# marker. The "(contact)" strip MUST run after toupper() and match upper-case (ExPORTER writes
# it lower-case, e.g. "LOOK, A THOMAS (contact)"); stripping it before/with the wrong case leaves
# "(CONTACT)" attached and breaks the join to the clean PI names in Author_Funding_Matches.
norm <- function(x) str_squish(gsub("\\(CONTACT\\)", "", gsub("[.]", "", toupper(x))))

au <- read_csv(au_file, show_col_types = FALSE)
# Grant "cores" (IC + serial, e.g. "HL126711") cited for the retracted authors.
cores <- unique(str_extract(au$Grant_ID, "[A-Z]{2}[0-9]{4,}$"))

# --- 1. Stream the ExPORTER project files; keep only cores we need, parsing the
#        parallel ";"-separated PI_NAMEs / PI_IDS into one row per (core, person). --
files <- list.files(raw_dir, "^RePORTER_PRJ_C_FY.*csv$", full.names = TRUE)
acc <- vector("list", length(files))
for (i in seq_along(files)) {
  d <- tryCatch(fread(files[i], select = c("CORE_PROJECT_NUM", "PI_NAMEs", "PI_IDS", "ORG_NAME"),
                      showProgress = FALSE), error = function(e) NULL)
  if (is.null(d)) next
  d[, core := str_extract(CORE_PROJECT_NUM, "[A-Z]{2}[0-9]{4,}")]
  d <- d[core %in% cores]
  if (nrow(d) == 0) next
  acc[[i]] <- as_tibble(d) %>%
    mutate(pair = map2(str_split(PI_NAMEs, ";"), str_split(PI_IDS, ";"),
      function(a, b) { n <- min(length(a), length(b))
        if (n == 0) return(tibble(pi_name = character(), pi_id = character()))
        tibble(pi_name = norm(a[seq_len(n)]),
               pi_id   = str_squish(gsub("\\(contact\\)", "", b[seq_len(n)]))) })) %>%
    select(core, ORG_NAME, pair) %>% unnest(pair) %>%
    filter(pi_name != "", pi_id != "", !is.na(pi_id)) %>%
    distinct(core, pi_name, pi_id, ORG_NAME)
}
cpo <- bind_rows(acc) %>% distinct(core, pi_name, pi_id, ORG_NAME)

# --- 2. Institution on the retracted paper, per author (via Record_ID). ------------
papers <- read_csv(pap_file, show_col_types = FALSE) %>%
  rename(Record_ID = `Record ID`) %>% select(Record_ID, Institution)
author_inst <- au %>% distinct(Original_Author_Name, Record_ID) %>%
  left_join(papers, by = "Record_ID") %>% filter(!is.na(Institution)) %>%
  distinct(Original_Author_Name, Institution)

# Lexical token set: upper-case BEFORE stripping non-letters (so mixed-case paper text
# is not reduced to its initial capitals); keep distinctive words (>3 chars, non-generic).
common <- c("UNIVERSITY","UNIV","COLLEGE","SCHOOL","MEDICAL","MEDICINE","CENTER","CENTRE",
  "HOSPITAL","INSTITUTE","INSTITUTION","DEPARTMENT","DEPT","SYSTEM","HEALTH","CARE","RESEARCH",
  "SCIENCE","SCIENCES","NATIONAL","STATE","UNITED","STATES","LABORATORY","FOUNDATION","DIVISION",
  "PROGRAM","CLINIC","CITY","NORTH","SOUTH","EAST","WEST")
toks <- function(s) { w <- unlist(str_split(gsub("[^A-Z ]", " ", toupper(s)), " "))
  unique(w[nchar(w) > 3 & !w %in% common]) }
inst_tok <- author_inst %>% group_by(Original_Author_Name) %>%
  summarise(it = list(toks(paste(Institution, collapse = " "))), .groups = "drop")

# --- 3. Map each (author, grant) to its candidate PI_IDs / ORG_NAMEs and test whether
#        each grant's awardee institution matches the retracted-paper institution. -----
ap <- au %>% mutate(core = str_extract(Grant_ID, "[A-Z]{2}[0-9]{4,}$"), pi_norm = norm(PI_NAME)) %>%
  distinct(Original_Author_Name, core, pi_norm) %>%
  left_join(cpo %>% rename(pi_norm = pi_name) %>% distinct(core, pi_norm, pi_id, ORG_NAME),
            by = c("core", "pi_norm"), relationship = "many-to-many") %>%
  left_join(inst_tok, by = "Original_Author_Name") %>%
  mutate(org_match = map2_lgl(ORG_NAME, it,
    ~ { if (is.null(.y) || is.na(.x)) return(FALSE); length(intersect(toks(.x), .y)) > 0 }))

# The REAL person's PI_ID(s): those with at least one institution-matching grant.
real_pid <- ap %>% filter(org_match) %>% distinct(Original_Author_Name, pi_id)

# --- 4. Author-level flags (n_pi_id collision flag; aff_match = any real PI_ID). -------
npi <- ap %>% group_by(Original_Author_Name) %>%
  summarise(n_pi_id = n_distinct(pi_id[!is.na(pi_id)]),
            n_grant_orgs = n_distinct(ORG_NAME[!is.na(ORG_NAME)]), .groups = "drop")
flags <- npi %>%
  mutate(aff_match = Original_Author_Name %in% real_pid$Original_Author_Name,
         exclude_consequences = (n_pi_id > 1) & !aff_match)
write_csv(flags %>% select(Original_Author_Name, n_pi_id, n_grant_orgs, aff_match, exclude_consequences),
          flags_file)

# --- 5. Grant-level keep flag. Non-collision authors keep every grant; collision authors
#        keep a grant only if it belongs to one of the real person's PI_IDs. ------------
is_coll <- flags %>% transmute(Original_Author_Name, is_collision = n_pi_id > 1)
grant_keep <- au %>%
  mutate(core = str_extract(Grant_ID, "[A-Z]{2}[0-9]{4,}$"), pi_norm = norm(PI_NAME)) %>%
  distinct(Original_Author_Name, Grant_ID, core, pi_norm) %>%
  left_join(cpo %>% rename(pi_norm = pi_name) %>% distinct(core, pi_norm, pi_id),
            by = c("core", "pi_norm"), relationship = "many-to-many") %>%
  left_join(real_pid %>% mutate(is_real = TRUE), by = c("Original_Author_Name", "pi_id")) %>%
  group_by(Original_Author_Name, Grant_ID) %>%
  summarise(belongs_real = any(coalesce(is_real, FALSE)), .groups = "drop") %>%
  left_join(is_coll, by = "Original_Author_Name") %>%
  mutate(is_collision = coalesce(is_collision, FALSE),
         keep_consequences = ifelse(is_collision, belongs_real, TRUE)) %>%
  select(Original_Author_Name, Grant_ID, is_collision, keep_consequences)
write_csv(grant_keep, keep_file)

n_grants_dropped <- sum(!grant_keep$keep_consequences)
n_authors_zeroed <- grant_keep %>% group_by(Original_Author_Name) %>%
  summarise(none = !any(keep_consequences), .groups = "drop") %>% pull(none) %>% sum()
cat(sprintf("Wrote %s and %s\n", flags_file, keep_file))
cat(sprintf("  authors: %d | collisions (n_pi_id>1): %d | with no institution match: %d\n",
  nrow(flags), sum(flags$n_pi_id > 1), sum(flags$exclude_consequences)))
cat(sprintf("  grant-level: %d of %d author-grant links dropped; %d authors lose all grants\n",
  n_grants_dropped, nrow(grant_keep), n_authors_zeroed))
