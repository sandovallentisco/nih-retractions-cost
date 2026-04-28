# ==============================================================================
# MASTER SCRIPT: DESCRIPTIVE STATISTICS & VISUALIZATION
# Description: Analyzes retraction trends, costs, and longitudinal funding 
#              impacts using NIH RePORTER and Retraction Watch data.
# ==============================================================================

# ------------------------------------------------------------------------------
# 0. SETUP & LIBRARIES
# ------------------------------------------------------------------------------
# Load required libraries
library(tidyverse) # Core data manipulation and ggplot2 visualizations
library(scales)    # Formatting numbers (dollars, commas)
library(quantmod)  # Financial data fetching (FRED API)
library(lubridate) # Date parsing

# Define file paths
papers_file <- "data/processed/FINAL_Retractions_Costs_and_Pubs.csv"
authors_file <- "data/processed/Author_Funding_Matches.csv"
plot_dir <- "data/processed/plots"

# Create plot directory if it doesn't exist
if (!dir.exists(plot_dir)) {
  dir.create(plot_dir, recursive = TRUE)
}

# ------------------------------------------------------------------------------
# 1. GLOBAL INFLATION ADJUSTMENT (FRED API)
# ------------------------------------------------------------------------------
cat("[INFO] Fetching historical CPI data from the Federal Reserve (FRED)...\n")
# Suppress warnings to keep the console clean during API connection
suppressWarnings(getSymbols("CPIAUCSL", src='FRED', auto.assign = TRUE)) 

# Convert the downloaded time series into a standard dataframe
cpi_df <- data.frame(Date = index(CPIAUCSL), CPI = coredata(CPIAUCSL))
colnames(cpi_df) <- c("Date", "CPI")

# Calculate the annual average CPI to avoid month-to-month volatility
annual_cpi <- cpi_df %>%
  mutate(Fiscal_Year = year(Date)) %>%
  group_by(Fiscal_Year) %>%
  summarise(CPI = mean(CPI, na.rm = TRUE))

# Determine the most recent CPI value to act as our baseline multiplier
current_cpi <- max(annual_cpi$CPI, na.rm = TRUE)

# Calculate the inflation multiplier for each historical year
annual_cpi <- annual_cpi %>%
  mutate(Inflation_Multiplier = current_cpi / CPI)


# ==============================================================================
# PART 1: PAPER-LEVEL ANALYSIS (Costs, Demographics, Reasons)
# ==============================================================================
cat("\n--- STARTING PART 1: PAPER-LEVEL ANALYSIS ---\n")

# Load the enriched Retraction Watch dataset
df_papers <- read_csv(papers_file, show_col_types = FALSE)

# ------------------------------------------------------------------------------
# 1.1 Data Cleaning & Feature Engineering
# ------------------------------------------------------------------------------
df_papers <- df_papers %>%
  mutate(
    # Extract the 4-digit year from the date strings using Regex
    Publication_Year = as.numeric(str_extract(OriginalPaperDate, "(?<=/)\\d{4}")),
    Retraction_Year = as.numeric(str_extract(RetractionDate, "(?<=/)\\d{4}")),
    
    # Calculate the time it took to retract the paper
    retraction_lag = Retraction_Year - Publication_Year,
    
    # Calculate Attributed Cost (Handling division by zero safely)
    attributed_cost_raw = ifelse(!is.na(Total_Grant_Pubs) & Total_Grant_Pubs > 0, 
                                 Total_NIH_Funding_Cost / Total_Grant_Pubs, 
                                 NA)
  ) %>%
  # Join with inflation data based on the Publication Year
  left_join(annual_cpi, by = c("Publication_Year" = "Fiscal_Year")) %>%
  # Calculate the final inflation-adjusted cost
  mutate(attributed_cost_adjusted = attributed_cost_raw * Inflation_Multiplier)

# ------------------------------------------------------------------------------
# 1.2 Summary Statistics Table (Attributed Costs)
# ------------------------------------------------------------------------------
cost_summary_df <- data.frame(
  Metric = c("Total Retracted Papers", "NIH Funded Papers", "Mean", "Median", "Q1", "Q3", "Total Funding Lost"),
  
  Raw_Attributed_Cost = c(
    nrow(df_papers), 
    sum(!is.na(df_papers$attributed_cost_raw)), 
    mean(df_papers$attributed_cost_raw, na.rm = TRUE),
    median(df_papers$attributed_cost_raw, na.rm = TRUE),
    quantile(df_papers$attributed_cost_raw, 0.25, na.rm = TRUE),
    quantile(df_papers$attributed_cost_raw, 0.75, na.rm = TRUE),
    sum(df_papers$attributed_cost_raw, na.rm = TRUE)
  ),
  
  Adjusted_Cost_Current = c(
    nrow(df_papers), 
    sum(!is.na(df_papers$attributed_cost_adjusted)),
    mean(df_papers$attributed_cost_adjusted, na.rm = TRUE),
    median(df_papers$attributed_cost_adjusted, na.rm = TRUE),
    quantile(df_papers$attributed_cost_adjusted, 0.25, na.rm = TRUE),
    quantile(df_papers$attributed_cost_adjusted, 0.75, na.rm = TRUE),
    sum(df_papers$attributed_cost_adjusted, na.rm = TRUE)
  )
)

# Format the table numbers for human readability
cost_summary_formatted <- cost_summary_df %>%
  mutate(
    Raw_Attributed_Cost = ifelse(Metric %in% c("Total Retracted Papers", "NIH Funded Papers"), 
                                 comma(Raw_Attributed_Cost), 
                                 dollar(Raw_Attributed_Cost, accuracy = 1)),
    
    Adjusted_Cost_Current = ifelse(Metric %in% c("Total Retracted Papers", "NIH Funded Papers"), 
                                   comma(Adjusted_Cost_Current), 
                                   dollar(Adjusted_Cost_Current, accuracy = 1))
  )

cat("\n[COST SUMMARY TABLE - FRED CPI ADJUSTED]\n")
print(cost_summary_formatted)

# Print Retraction Lag Summary
lag_clean <- na.omit(df_papers$retraction_lag)
cat("\n[RETRACTION LAG SUMMARY (Years)]\n")
cat(sprintf("  Valid papers: %d\n", length(lag_clean)))
cat(sprintf("  Mean: %.2f | Median: %.2f\n", mean(lag_clean), median(lag_clean)))

# ------------------------------------------------------------------------------
# 1.3 Universal Plot Theme
# ------------------------------------------------------------------------------
# A shared transparent and minimalist theme for the dashboard
dashboard_theme <- theme_classic(base_size = 14) + 
  theme(
    legend.position = "top",
    plot.background = element_rect(fill = "transparent", color = NA),
    panel.background = element_rect(fill = "transparent", color = NA),
    legend.background = element_rect(fill = "transparent", color = NA),
    legend.box.background = element_rect(fill = "transparent", color = NA)
  )

corporate_colors <- c("NIH Funded" = "#005b96", "Not NIH Funded / Other" = "gray70")

# ------------------------------------------------------------------------------
# 1.4 Generate Categorical Plots (Years, Publishers, Domains, Reasons)
# ------------------------------------------------------------------------------

# --- PLOT 1: Publication Year Distribution ---
cat("[INFO] Generating Publication Year Histogram...\n")
plot_pub_year <- df_papers %>%
  drop_na(Publication_Year) %>%
  filter(Publication_Year >= 1970) %>%
  mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, 
                                 "NIH Funded", "Not NIH Funded / Other")) %>%
  ggplot(aes(x = Publication_Year, fill = Funding_Status)) +
  geom_histogram(binwidth = 1, color = "white", position = "stack") +
  scale_x_continuous(breaks = seq(1970, 2026, by = 5)) + 
  scale_fill_manual(values = corporate_colors) +
  labs(title = "Distribution of Original Publication Years (1970-2026)",
       subtitle = "Stacked by NIH funding presence. Note: Pre-1970 outliers excluded.",
       x = "Publication Year", 
       y = "Number of Retracted Papers",
       fill = "Funding Status") +
  dashboard_theme

ggsave(file.path(plot_dir, "Publication_Year_Histogram.png"), plot = plot_pub_year, width = 10, height = 6, dpi = 300, bg = "transparent")

# --- PLOT 2: Retraction Year Distribution ---
cat("[INFO] Generating Retraction Year Histogram...\n")
plot_ret_year <- df_papers %>%
  drop_na(Retraction_Year) %>%
  filter(Retraction_Year >= 1970) %>%
  mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, 
                                 "NIH Funded", "Not NIH Funded / Other")) %>%
  ggplot(aes(x = Retraction_Year, fill = Funding_Status)) +
  geom_histogram(binwidth = 1, color = "white", position = "stack") +
  scale_x_continuous(breaks = seq(1970, 2026, by = 5)) + 
  scale_fill_manual(values = corporate_colors) +
  labs(title = "Distribution of Retraction Years (1970-2026)",
       subtitle = "Stacked by NIH funding presence. Note: Pre-1970 outliers excluded.",
       x = "Retraction Year", 
       y = "Number of Retractions",
       fill = "Funding Status") +
  dashboard_theme

ggsave(file.path(plot_dir, "Retraction_Year_Histogram.png"), plot = plot_ret_year, width = 10, height = 6, dpi = 300, bg = "transparent")

# --- PLOT 3: Top 20 Publishers ---
cat("[INFO] Generating Publishers Plot...\n")
publishers_data <- df_papers %>%
  drop_na(Publisher) %>%
  mutate(Publisher = str_trim(Publisher)) %>%
  filter(Publisher != "") %>%
  mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, 
                                 "NIH Funded", "Not NIH Funded / Other"))

total_publishers <- n_distinct(publishers_data$Publisher)

top_20_publishers <- publishers_data %>%
  count(Publisher, sort = TRUE) %>%
  slice_head(n = 20) %>%
  pull(Publisher)

plot_publishers <- publishers_data %>%
  filter(Publisher %in% top_20_publishers) %>%
  mutate(Publisher = factor(Publisher, levels = rev(top_20_publishers))) %>%
  ggplot(aes(x = Publisher, fill = Funding_Status)) +
  geom_bar(color = "white", position = "stack") +
  coord_flip() +
  scale_fill_manual(values = corporate_colors) +
  labs(title = "Top 20 Publishers by Number of Retracted Papers",
       subtitle = sprintf("Top 20 out of %d total publishers. Stacked by NIH funding.", total_publishers),
       x = NULL, 
       y = "Number of Retracted Papers",
       fill = "Funding Status") +
  dashboard_theme + 
  theme(axis.text.y = element_text(size = 10, face = "bold", color = "#333333"))

ggsave(file.path(plot_dir, "Top_20_Publishers.png"), plot = plot_publishers, width = 11, height = 8, dpi = 300, bg = "transparent")

# --- PLOT: Scientific Domains ---
cat("\n[INFO] Generating Scientific Domains Plot...\n")
domains_data <- df_papers %>%
  drop_na(Subject) %>%
  mutate(Paper_ID = row_number()) %>%
  separate_rows(Subject, sep = ";") %>%
  mutate(Subject = str_trim(Subject)) %>%
  filter(Subject != "") %>%
  mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, 
                                 "NIH Funded", "Not NIH Funded / Other")) %>%
  mutate(Domain_Acronym = str_remove_all(str_extract(Subject, "^\\([^)]+\\)"), "[()]")) %>%
  mutate(Domain_Full = case_when(
    Domain_Acronym == "BLS" ~ "Biological & Life Sciences (BLS)",
    Domain_Acronym == "HSC" ~ "Health Sciences (HSC)",
    Domain_Acronym == "PHY" ~ "Physical Sciences (PHY)",
    Domain_Acronym == "ENV" ~ "Environmental Sciences (ENV)",
    Domain_Acronym == "B/T" ~ "Business & Technology (B/T)",
    Domain_Acronym == "SOC" ~ "Social Sciences (SOC)",
    Domain_Acronym == "HUM" ~ "Humanities (HUM)",
    TRUE ~ Domain_Acronym
  )) %>%
  distinct(Paper_ID, Domain_Full, Funding_Status)

domain_order <- domains_data %>% count(Domain_Full, sort = TRUE) %>% pull(Domain_Full)

plot_domains <- domains_data %>%
  mutate(Domain_Full = factor(Domain_Full, levels = rev(domain_order))) %>%
  ggplot(aes(x = Domain_Full, fill = Funding_Status)) +
  geom_bar(color = "white", position = "stack") +
  coord_flip() +
  scale_fill_manual(values = corporate_colors) +
  labs(title = "Retracted Papers by Major Scientific Domain",
       subtitle = "Stacked by NIH funding. Multiple subjects per domain counted once.",
       x = NULL, y = "Number of Unique Retracted Papers", fill = "Funding Status") +
  dashboard_theme + theme(axis.text.y = element_text(size = 11, face = "bold", color = "#333333"))

ggsave(file.path(plot_dir, "Domain_Frequencies.png"), plot = plot_domains, width = 11, height = 6, dpi = 300, bg = "transparent")

# --- PLOT: Top 10 Reasons for Retraction ---
cat("[INFO] Generating Reasons for Retraction Plot...\n")
reasons_data <- df_papers %>%
  drop_na(Reason) %>%
  mutate(Paper_ID = row_number()) %>% 
  separate_rows(Reason, sep = ";") %>%
  mutate(Reason = str_trim(Reason)) %>%
  filter(Reason != "") %>%
  # Exclude procedural tags (e.g., "Investigation by Journal") to focus on actual causes
  filter(!str_detect(Reason, "^Investigation")) %>%
  mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, 
                                 "NIH Funded", "Not NIH Funded / Other")) %>%
  distinct(Paper_ID, Reason, Funding_Status)

top_10_reasons <- reasons_data %>% count(Reason, sort = TRUE) %>% slice_head(n = 10) %>% pull(Reason)

plot_reasons <- reasons_data %>%
  filter(Reason %in% top_10_reasons) %>%
  mutate(Reason = factor(Reason, levels = rev(top_10_reasons))) %>%
  ggplot(aes(x = Reason, fill = Funding_Status)) +
  geom_bar(color = "white", position = "stack") +
  coord_flip() +
  scale_fill_manual(values = corporate_colors) +
  labs(title = "Top 10 Most Common Reasons for Retraction",
       subtitle = "Stacked by NIH funding. Procedural 'Investigation' tags excluded.",
       x = NULL, y = "Number of Retracted Papers", fill = "Funding Status") +
  dashboard_theme + theme(axis.text.y = element_text(size = 11, face = "bold", color = "#333333"))

ggsave(file.path(plot_dir, "Top_10_Reasons.png"), plot = plot_reasons, width = 12, height = 6, dpi = 300, bg = "transparent")

# ==============================================================================
# PART 2: LONGITUDINAL AUTHOR IMPACT (Survival & Funding Contraction)
# ==============================================================================
cat("\n--- STARTING PART 2: LONGITUDINAL AUTHOR IMPACT ---\n")

# Load the matching file containing full historical grants for retracted authors
df_authors_raw <- read_csv(authors_file, show_col_types = FALSE)

# ------------------------------------------------------------------------------
# 2.1 Timeline Data Preparation
# ------------------------------------------------------------------------------
df_authors <- df_authors_raw %>%
  group_by(Original_Author_Name) %>%
  # Lock the "Index Event" to the author's very first retraction year
  mutate(First_Retraction_Year = min(Retraction_Year, na.rm = TRUE)) %>%
  ungroup() %>%
  # Calculate relative years (e.g., -2 years before scandal, +1 year after)
  mutate(diff_retracted = Fiscal_Year - First_Retraction_Year) %>%
  # Deduplicate to avoid summing the same grant multiple times for repeat offenders
  distinct(Original_Author_Name, Grant_ID, Fiscal_Year, Funding_Amount, diff_retracted) %>%
  # Apply inflation to all historical grants
  left_join(annual_cpi, by = "Fiscal_Year") %>%
  mutate(Funding_Adjusted = Funding_Amount * Inflation_Multiplier)

# Define the analysis window (±3 years)
analysis_window <- 3  

# Aggregate data by relative year
df_timeline <- df_authors %>%
  filter(diff_retracted >= -analysis_window & diff_retracted <= analysis_window) %>%
  group_by(diff_retracted) %>%
  summarise(
    Total_Adjusted_Funding = sum(Funding_Adjusted, na.rm = TRUE),
    Total_Grants = n_distinct(Grant_ID),           
    Active_Authors = n_distinct(Original_Author_Name), 
    Average_Funding_Per_Author = Total_Adjusted_Funding / Active_Authors 
  ) %>%
  # Label the exact year of the scandal for visualization purposes
  mutate(Period_Label = ifelse(diff_retracted == 0, "Retraction Year (0)", "Normal Years"))

timeline_colors <- c("Retraction Year (0)" = "#cccccc", "Normal Years" = "#005b96")

# ------------------------------------------------------------------------------
# 2.2 Longitudinal Impact Plots
# ------------------------------------------------------------------------------
cat("[INFO] Generating Longitudinal Impact Plots...\n")

# --- PLOT: Total Attributed Funding ---
coeff_total <- max(df_timeline$Total_Adjusted_Funding) / max(df_timeline$Active_Authors)

plot_total_funding <- ggplot(df_timeline, aes(x = diff_retracted)) +
  geom_col(aes(y = Total_Adjusted_Funding, fill = Period_Label), color = "black", width = 0.8) +
  geom_line(aes(y = Active_Authors * coeff_total), color = "black", linewidth = 1) +
  geom_point(aes(y = Active_Authors * coeff_total), color = "black", size = 2.5) +
  scale_fill_manual(values = timeline_colors) +
  scale_y_continuous(labels = label_dollar(), name = "Total Attributed Funding (USD)",
                     sec.axis = sec_axis(~./coeff_total, name = "Active Authors (Survival)")) +
  labs(title = "Total Systemic Funding Contraction",
       subtitle = "The absolute financial footprint of the affected cohort drops over time.",
       x = "Years Relative to First Retraction") +
  theme_minimal(base_size = 14) + theme(legend.position = "none", panel.grid.major.x = element_blank())

# --- PLOT: Average Funding per Author ---
coeff_avg <- max(df_timeline$Average_Funding_Per_Author) / max(df_timeline$Active_Authors)

plot_avg_funding <- ggplot(df_timeline, aes(x = diff_retracted)) +
  geom_col(aes(y = Average_Funding_Per_Author, fill = Period_Label), color = "black", width = 0.8) +
  geom_line(aes(y = Active_Authors * coeff_avg), color = "black", linewidth = 1) +
  geom_point(aes(y = Active_Authors * coeff_avg), color = "black", size = 2.5) +
  scale_fill_manual(values = timeline_colors) +
  scale_y_continuous(labels = label_dollar(), name = "Average Funding per Author (USD)",
                     sec.axis = sec_axis(~./coeff_avg, name = "Active Authors (Survival)")) +
  labs(title = "Average Funding per Active Author",
       subtitle = "Remains stable post-scandal due to survivorship bias.",
       x = "Years Relative to First Retraction") +
  theme_minimal(base_size = 14) + theme(legend.position = "none", panel.grid.major.x = element_blank())

ggsave(file.path(plot_dir, "Impact_Total_Funding.png"), plot = plot_total_funding, width = 10, height = 6, dpi = 300)
ggsave(file.path(plot_dir, "Impact_Average_Funding.png"), plot = plot_avg_funding, width = 10, height = 6, dpi = 300)

# ------------------------------------------------------------------------------
# 2.3 Statistical Significance (Pre vs Post ±3 Years)
# ------------------------------------------------------------------------------
# Prepare paired data at the author level to test institutional punishment
df_stats_paired <- df_authors %>%
  filter(diff_retracted >= -analysis_window & diff_retracted <= analysis_window & diff_retracted != 0) %>%
  mutate(Period = ifelse(diff_retracted < 0, "Pre", "Post")) %>%
  group_by(Original_Author_Name, Period) %>%
  summarise(
    Annual_Funding = sum(Funding_Adjusted, na.rm = TRUE) / analysis_window,
    Total_Grants = n_distinct(Grant_ID),
    .groups = "drop"
  ) %>%
  # Pivot to wide format. Missing periods (authors who were expelled) are filled with 0
  pivot_wider(names_from = Period, values_from = c(Annual_Funding, Total_Grants), values_fill = 0)

cat("\n[STATISTICAL SIGNIFICANCE - WILCOXON SIGNED-RANK TEST]\n")

# Test 1: Financial Punishment
test_funding <- wilcox.test(df_stats_paired$Annual_Funding_Pre, df_stats_paired$Annual_Funding_Post, paired = TRUE, exact = FALSE)
cat(sprintf("1. Annual Funding Change (p-value): %e\n", test_funding$p.value))

# Test 2: Project Cancellation
test_grants <- wilcox.test(df_stats_paired$Total_Grants_Pre, df_stats_paired$Total_Grants_Post, paired = TRUE, exact = FALSE)
cat(sprintf("2. Active Grants Volume Change (p-value): %e\n", test_grants$p.value))

cat("\n[!] Script executed successfully. All plots saved to data/processed/plots.\n")