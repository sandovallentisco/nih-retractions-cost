# ==============================================================================
# SHINY DASHBOARD: NIH Retraction & Funding Impact (NIH RePORTER Clone)
# ==============================================================================

# 1. LIBRERÍAS Y SETUP GLOBAL
# ------------------------------------------------------------------------------
library(shiny)
library(tidyverse)
library(scales)
library(quantmod)
library(lubridate)
library(DT)               
library(plotly)           
library(shinycssloaders)  

# --- RUTAS DE ARCHIVOS ---
papers_file <- "data/processed/FINAL_Retractions_Costs_and_Pubs.csv"
authors_file <- "data/processed/Author_Funding_Matches.csv"

# --- PROCESAMIENTO DE DATOS ---
cpi_df <- tryCatch({
  suppressWarnings(getSymbols("CPIAUCSL", src='FRED', auto.assign = FALSE)) 
  data.frame(Date = index(CPIAUCSL), CPI = coredata(CPIAUCSL))
}, error = function(e) {
  warning("No se pudo conectar a FRED. Usando datos de inflación simulados por defecto.")
  data.frame(Date = seq(as.Date("1970-01-01"), by = "year", length.out = 60), 
             CPI = seq(38, 310, length.out = 60))
})

colnames(cpi_df) <- c("Date", "CPI")

annual_cpi <- cpi_df %>%
  mutate(Fiscal_Year = year(Date)) %>%
  group_by(Fiscal_Year) %>%
  summarise(CPI = mean(CPI, na.rm = TRUE), .groups = "drop")
current_cpi <- max(annual_cpi$CPI, na.rm = TRUE)
annual_cpi <- annual_cpi %>% mutate(Inflation_Multiplier = current_cpi / CPI)

# Cargar datos de papers
df_papers <- read_csv(papers_file, show_col_types = FALSE) %>%
  mutate(
    Publication_Year = as.numeric(str_extract(OriginalPaperDate, "(?<=/)\\d{4}")),
    Retraction_Year = as.numeric(str_extract(RetractionDate, "(?<=/)\\d{4}")),
    retraction_lag = Retraction_Year - Publication_Year,
    attributed_cost_raw = ifelse(!is.na(Total_Grant_Pubs) & Total_Grant_Pubs > 0, 
                                 Total_NIH_Funding_Cost / Total_Grant_Pubs, NA)
  ) %>%
  left_join(annual_cpi, by = c("Publication_Year" = "Fiscal_Year")) %>%
  mutate(attributed_cost_adjusted = attributed_cost_raw * Inflation_Multiplier)

# Cargar datos de autores
df_authors_raw <- read_csv(authors_file, show_col_types = FALSE)
df_authors <- df_authors_raw %>%
  group_by(Original_Author_Name) %>%
  mutate(First_Retraction_Year = min(Retraction_Year, na.rm = TRUE)) %>%
  ungroup() %>%
  mutate(diff_retracted = Fiscal_Year - First_Retraction_Year) %>%
  distinct(Original_Author_Name, Grant_ID, Fiscal_Year, Funding_Amount, diff_retracted) %>%
  left_join(annual_cpi, by = "Fiscal_Year") %>%
  mutate(Funding_Adjusted = Funding_Amount * Inflation_Multiplier)

# Configuración visual global para gráficos (Fondo transparente para que coincida con las tarjetas)
dashboard_theme <- theme_classic(base_size = 12) + 
  theme(
    legend.position = "top", 
    legend.title = element_blank(),
    plot.background = element_rect(fill = "transparent", color = NA),
    panel.background = element_rect(fill = "transparent", color = NA)
  )
corporate_colors <- c("NIH Funded" = "#005b96", "Not NIH Funded / Other" = "gray70")


# 2. CSS PERSONALIZADO (CLONANDO NIH REPORTER)
# ------------------------------------------------------------------------------
nih_css <- "
  /* Fondo general gris claro */
  body { background-color: #f4f6f9; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
  
  /* Barra de navegación superior oscura */
  .navbar-inverse { background-color: #2b2b2b; border-color: #1a1a1a; }
  .navbar-inverse .navbar-brand { color: #ffffff; font-weight: bold; font-size: 22px; }
  .navbar-inverse .navbar-nav>li>a { color: #dddddd; font-weight: bold; }
  .navbar-inverse .navbar-nav>li>a:hover { color: #ffffff; }
  
  /* Banner interactivo estilo NIH (Degradado azul/teal) */
  .hero-banner {
    background: linear-gradient(135deg, #09375e 0%, #13778a 100%);
    color: white;
    padding: 40px 30px;
    margin-top: -20px; /* Para pegarlo a la barra de navegacion */
    margin-bottom: 30px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
  }
  .hero-banner h2 { margin-top: 0; font-weight: bold; }
  .kpi-box {
    background: rgba(255, 255, 255, 0.15);
    border: 1px solid rgba(255, 255, 255, 0.3);
    border-radius: 5px;
    padding: 15px;
    text-align: center;
  }
  .kpi-box h3 { margin: 0; font-size: 28px; font-weight: bold; }
  .kpi-box p { margin: 0; font-size: 14px; text-transform: uppercase; }

  /* Tarjetas blancas con borde superior celeste (El look exacto de la foto) */
  .nih-card {
    background: white;
    border-radius: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
    border-top: 4px solid #17a2b8; 
    padding: 20px;
    margin-bottom: 25px;
  }
  .nih-card h4 { 
    color: #333; 
    font-weight: bold; 
    margin-top: 0; 
    margin-bottom: 20px;
    font-size: 18px;
  }
"

# 3. INTERFAZ DE USUARIO (UI)
# ------------------------------------------------------------------------------
ui <- navbarPage(
  title = "NIH RePORT | Impact Analysis",
  inverse = TRUE, # Hace la barra superior oscura
  header = tags$head(tags$style(HTML(nih_css))), # Inyecta nuestro CSS clonado
  
  # --- PESTAÑA 1: Resumen ---
  tabPanel("Summary Stats",
           # HERO BANNER (Cinta azul superior)
           fluidRow(
             column(12,
                    div(class = "hero-banner",
                        fluidRow(
                          column(4, 
                                 h2("Welcome to the Impact Dashboard"),
                                 p("Analyzing the financial and scientific footprint of retracted research funded by the NIH.")
                          ),
                          column(8,
                                 fluidRow(
                                   column(4, div(class = "kpi-box", p("Retracted Papers"), h3(textOutput("kpi_papers")))),
                                   column(4, div(class = "kpi-box", p("NIH Funded"), h3(textOutput("kpi_nih_papers")))),
                                   column(4, div(class = "kpi-box", p("Adj. Funding Lost"), h3(textOutput("kpi_funding"))))
                                 )
                          )
                        )
                    )
             )
           ),
           # CONTENIDO (Tarjetas)
           fluidPage(
             fluidRow(
               column(8,
                      div(class = "nih-card",
                          h4("Cost & Retraction Summary (FRED CPI Adjusted)"),
                          withSpinner(DTOutput("cost_summary_table"), type = 4, color = "#17a2b8")
                      )
               ),
               column(4,
                      div(class = "nih-card",
                          h4("Statistical Significance (Wilcoxon Test)"),
                          withSpinner(verbatimTextOutput("stats_output"), type = 4, color = "#17a2b8")
                      )
               )
             )
           )
  ),
  
  # --- PESTAÑA 2: Análisis de Papers ---
  tabPanel("Paper Analysis",
           fluidPage(
             br(), # Espacio extra superior
             fluidRow(
               column(6, div(class = "nih-card", h4("Publication Year"), withSpinner(plotlyOutput("plot_pub_year"), type = 4, color = "#17a2b8"))),
               column(6, div(class = "nih-card", h4("Retraction Year"), withSpinner(plotlyOutput("plot_ret_year"), type = 4, color = "#17a2b8")))
             ),
             fluidRow(
               column(6, div(class = "nih-card", h4("Top Publishers"), withSpinner(plotlyOutput("plot_publishers"), type = 4, color = "#17a2b8"))),
               column(6, div(class = "nih-card", h4("Scientific Domains"), withSpinner(plotlyOutput("plot_domains"), type = 4, color = "#17a2b8")))
             ),
             fluidRow(
               column(12, div(class = "nih-card", h4("Top 10 Reasons for Retraction"), withSpinner(plotlyOutput("plot_reasons"), type = 4, color = "#17a2b8")))
             )
           )
  ),
  
  # --- PESTAÑA 3: Impacto Longitudinal ---
  tabPanel("Longitudinal Impact",
           fluidPage(
             br(),
             fluidRow(
               column(12, p(strong("Note:"), " Dual-axis charts are kept in high-res static format for best visualization of trends.", style = "color: gray; font-style: italic; margin-bottom: 20px;"))
             ),
             fluidRow(
               column(6, div(class = "nih-card", h4("Total Funding Contraction"), withSpinner(plotOutput("plot_total_funding"), type = 4, color = "#17a2b8"))),
               column(6, div(class = "nih-card", h4("Average Funding per Author"), withSpinner(plotOutput("plot_avg_funding"), type = 4, color = "#17a2b8")))
             )
           )
  )
)

# 4. LÓGICA DEL SERVIDOR (Server)
# ------------------------------------------------------------------------------
# (La lógica del servidor se mantiene exactamente igual para garantizar que todo funcione correctamente)
server <- function(input, output, session) {
  
  # --- KPIs SUPERIORES ---
  output$kpi_papers <- renderText({ comma(nrow(df_papers)) })
  output$kpi_funding <- renderText({ dollar(sum(df_papers$attributed_cost_adjusted, na.rm = TRUE), accuracy = 1) })
  output$kpi_nih_papers <- renderText({ comma(sum(!is.na(df_papers$attributed_cost_raw))) })
  
  # --- TABLA DE RESUMEN ---
  output$cost_summary_table <- renderDT({
    cost_summary_df <- data.frame(
      Metric = c("Total Retracted Papers", "NIH Funded Papers", "Mean", "Median", "Q1", "Q3", "Total Funding Lost"),
      Raw_Attributed_Cost = c(
        nrow(df_papers), sum(!is.na(df_papers$attributed_cost_raw)), 
        mean(df_papers$attributed_cost_raw, na.rm = TRUE), median(df_papers$attributed_cost_raw, na.rm = TRUE),
        quantile(df_papers$attributed_cost_raw, 0.25, na.rm = TRUE), quantile(df_papers$attributed_cost_raw, 0.75, na.rm = TRUE),
        sum(df_papers$attributed_cost_raw, na.rm = TRUE)
      ),
      Adjusted_Cost_Current = c(
        nrow(df_papers), sum(!is.na(df_papers$attributed_cost_adjusted)),
        mean(df_papers$attributed_cost_adjusted, na.rm = TRUE), median(df_papers$attributed_cost_adjusted, na.rm = TRUE),
        quantile(df_papers$attributed_cost_adjusted, 0.25, na.rm = TRUE), quantile(df_papers$attributed_cost_adjusted, 0.75, na.rm = TRUE),
        sum(df_papers$attributed_cost_adjusted, na.rm = TRUE)
      )
    ) %>%
      mutate(
        Raw_Attributed_Cost = ifelse(Metric %in% c("Total Retracted Papers", "NIH Funded Papers"), comma(Raw_Attributed_Cost), dollar(Raw_Attributed_Cost, accuracy = 1)),
        Adjusted_Cost_Current = ifelse(Metric %in% c("Total Retracted Papers", "NIH Funded Papers"), comma(Adjusted_Cost_Current), dollar(Adjusted_Cost_Current, accuracy = 1))
      )
    
    datatable(cost_summary_df, 
              extensions = 'Buttons',
              options = list(
                dom = 'Brtip',
                buttons = c('copy', 'csv', 'excel'),
                paging = FALSE,
                className = 'compact stripe hover'
              ),
              rownames = FALSE)
  })
  
  # --- GRÁFICOS NIVEL PAPER (Plotly) ---
  output$plot_pub_year <- renderPlotly({
    p <- df_papers %>% drop_na(Publication_Year) %>% filter(Publication_Year >= 1970) %>%
      mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, "NIH Funded", "Not NIH Funded / Other")) %>%
      ggplot(aes(x = Publication_Year, fill = Funding_Status)) +
      geom_histogram(binwidth = 1, color = "white", position = "stack") +
      scale_fill_manual(values = corporate_colors) + 
      labs(x = "Publication Year", y = "Count") + dashboard_theme
    ggplotly(p, tooltip = c("x", "y", "fill")) %>% layout(legend = list(orientation = "h", x = 0, y = 1.1))
  })
  
  output$plot_ret_year <- renderPlotly({
    p <- df_papers %>% drop_na(Retraction_Year) %>% filter(Retraction_Year >= 1970) %>%
      mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, "NIH Funded", "Not NIH Funded / Other")) %>%
      ggplot(aes(x = Retraction_Year, fill = Funding_Status)) +
      geom_histogram(binwidth = 1, color = "white", position = "stack") +
      scale_fill_manual(values = corporate_colors) + 
      labs(x = "Retraction Year", y = "Count") + dashboard_theme
    ggplotly(p, tooltip = c("x", "y", "fill")) %>% layout(legend = list(orientation = "h", x = 0, y = 1.1))
  })
  
  output$plot_publishers <- renderPlotly({
    publishers_data <- df_papers %>% drop_na(Publisher) %>% mutate(Publisher = str_trim(Publisher)) %>% filter(Publisher != "") %>%
      mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, "NIH Funded", "Not NIH Funded / Other"))
    top_20 <- publishers_data %>% count(Publisher, sort = TRUE) %>% slice_head(n = 20) %>% pull(Publisher)
    p <- publishers_data %>% filter(Publisher %in% top_20) %>%
      mutate(Publisher = factor(Publisher, levels = rev(top_20))) %>%
      ggplot(aes(x = Publisher, fill = Funding_Status)) +
      geom_bar(color = "white", position = "stack") + coord_flip() +
      scale_fill_manual(values = corporate_colors) + labs(x = "", y = "Count") + dashboard_theme
    ggplotly(p, tooltip = c("y", "fill", "count")) %>% layout(legend = list(orientation = "h", x = 0, y = 1.1))
  })
  
  output$plot_domains <- renderPlotly({
    domains_data <- df_papers %>% drop_na(Subject) %>% mutate(Paper_ID = row_number()) %>%
      separate_rows(Subject, sep = ";") %>% mutate(Subject = str_trim(Subject)) %>% filter(Subject != "") %>%
      mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, "NIH Funded", "Not NIH Funded / Other"),
             Domain_Acronym = str_remove_all(str_extract(Subject, "^\\([^)]+\\)"), "[()]")) %>%
      mutate(Domain_Full = case_when(Domain_Acronym == "BLS" ~ "Biological & Life Sciences", Domain_Acronym == "HSC" ~ "Health Sciences",
                                     Domain_Acronym == "PHY" ~ "Physical Sciences", TRUE ~ Domain_Acronym)) %>%
      distinct(Paper_ID, Domain_Full, Funding_Status)
    domain_order <- domains_data %>% count(Domain_Full, sort = TRUE) %>% pull(Domain_Full)
    p <- domains_data %>% mutate(Domain_Full = factor(Domain_Full, levels = rev(domain_order))) %>%
      ggplot(aes(x = Domain_Full, fill = Funding_Status)) + geom_bar(color = "white", position = "stack") + coord_flip() +
      scale_fill_manual(values = corporate_colors) + labs(x = "", y = "Count") + dashboard_theme
    ggplotly(p, tooltip = c("y", "fill", "count")) %>% layout(legend = list(orientation = "h", x = 0, y = 1.1))
  })
  
  output$plot_reasons <- renderPlotly({
    reasons_data <- df_papers %>% drop_na(Reason) %>% mutate(Paper_ID = row_number()) %>% separate_rows(Reason, sep = ";") %>%
      mutate(Reason = str_trim(Reason)) %>% filter(Reason != "", !str_detect(Reason, "^Investigation")) %>%
      mutate(Funding_Status = ifelse(!is.na(Total_NIH_Funding_Cost) & Total_NIH_Funding_Cost > 0, "NIH Funded", "Not NIH Funded / Other")) %>%
      distinct(Paper_ID, Reason, Funding_Status)
    top_10 <- reasons_data %>% count(Reason, sort = TRUE) %>% slice_head(n = 10) %>% pull(Reason)
    p <- reasons_data %>% filter(Reason %in% top_10) %>% mutate(Reason = factor(Reason, levels = rev(top_10))) %>%
      ggplot(aes(x = Reason, fill = Funding_Status)) + geom_bar(color = "white", position = "stack") + coord_flip() +
      scale_fill_manual(values = corporate_colors) + labs(x = "", y = "Count") + dashboard_theme
    ggplotly(p, tooltip = c("y", "fill", "count")) %>% layout(legend = list(orientation = "h", x = 0, y = 1.1))
  })
  
  # --- IMPACTO LONGITUDINAL ---
  df_timeline <- reactive({
    df_authors %>% filter(diff_retracted >= -3 & diff_retracted <= 3) %>%
      group_by(diff_retracted) %>%
      summarise(Total_Adjusted_Funding = sum(Funding_Adjusted, na.rm = TRUE), Active_Authors = n_distinct(Original_Author_Name)) %>%
      mutate(Average_Funding_Per_Author = Total_Adjusted_Funding / Active_Authors,
             Period_Label = ifelse(diff_retracted == 0, "Retraction Year (0)", "Normal Years"))
  })
  timeline_colors <- c("Retraction Year (0)" = "#cccccc", "Normal Years" = "#005b96")
  
  output$plot_total_funding <- renderPlot({
    tl <- df_timeline()
    coeff_total <- max(tl$Total_Adjusted_Funding) / max(tl$Active_Authors)
    ggplot(tl, aes(x = diff_retracted)) +
      geom_col(aes(y = Total_Adjusted_Funding, fill = Period_Label), color = "black", width = 0.8) +
      geom_line(aes(y = Active_Authors * coeff_total), color = "black", linewidth = 1) +
      geom_point(aes(y = Active_Authors * coeff_total), color = "black", size = 3) +
      scale_fill_manual(values = timeline_colors) + scale_x_continuous(breaks = -3:3) +
      scale_y_continuous(labels = label_dollar(), sec.axis = sec_axis(~./coeff_total, name = "Active Authors")) +
      labs(x = "Years from First Retraction", y = "Total Adjusted Funding") +
      theme_minimal(base_size = 14) + theme(legend.position = "none", panel.grid.minor = element_blank())
  })
  
  output$plot_avg_funding <- renderPlot({
    tl <- df_timeline()
    coeff_avg <- max(tl$Average_Funding_Per_Author) / max(tl$Active_Authors)
    ggplot(tl, aes(x = diff_retracted)) +
      geom_col(aes(y = Average_Funding_Per_Author, fill = Period_Label), color = "black", width = 0.8) +
      geom_line(aes(y = Active_Authors * coeff_avg), color = "black", linewidth = 1) +
      geom_point(aes(y = Active_Authors * coeff_avg), color = "black", size = 3) +
      scale_fill_manual(values = timeline_colors) + scale_x_continuous(breaks = -3:3) +
      scale_y_continuous(labels = label_dollar(), sec.axis = sec_axis(~./coeff_avg, name = "Active Authors")) +
      labs(x = "Years from First Retraction", y = "Average Funding Per Author") +
      theme_minimal(base_size = 14) + theme(legend.position = "none", panel.grid.minor = element_blank())
  })
  
  # --- PRUEBAS ESTADÍSTICAS ---
  output$stats_output <- renderPrint({
    df_stats_paired <- df_authors %>% filter(diff_retracted >= -3 & diff_retracted <= 3 & diff_retracted != 0) %>%
      mutate(Period = ifelse(diff_retracted < 0, "Pre", "Post")) %>% group_by(Original_Author_Name, Period) %>%
      summarise(Annual_Funding = sum(Funding_Adjusted, na.rm = TRUE) / 3, Total_Grants = n_distinct(Grant_ID), .groups = "drop") %>%
      pivot_wider(names_from = Period, values_from = c(Annual_Funding, Total_Grants), values_fill = list(Annual_Funding = 0, Total_Grants = 0))
    test_funding <- wilcox.test(df_stats_paired$Annual_Funding_Pre, df_stats_paired$Annual_Funding_Post, paired = TRUE, exact = FALSE)
    test_grants <- wilcox.test(df_stats_paired$Total_Grants_Pre, df_stats_paired$Total_Grants_Post, paired = TRUE, exact = FALSE)
    
    cat("WILCOXON SIGNED-RANK TEST (PAIRED)\n")
    cat("Comparing 3 Years Pre-Retraction vs Post-Retraction\n")
    cat("--------------------------------------------------\n\n")
    cat(sprintf("1. Annual Funding Change p-value: %s\n", format(test_funding$p.value, scientific = TRUE, digits = 4)))
    cat(sprintf("2. Active Grants Volume p-value:  %s\n", format(test_grants$p.value, scientific = TRUE, digits = 4)))
  })
}

# 4. EJECUTAR APP
# ------------------------------------------------------------------------------
shinyApp(ui = ui, server = server)