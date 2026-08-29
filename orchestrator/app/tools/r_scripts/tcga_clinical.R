#!/usr/bin/env Rscript
# Real TCGAbiolinks::GDCquery_clinic call (Bioconductor) -- hits the
# real GDC REST API directly (api.gdc.cancer.gov), no BAM/expression
# file downloads. Same Rscript-subprocess pattern as
# cluster_profiler_enrich.R -- see app/tools/tcga_clinical.py.
#
# Args: <project> <output_csv>
suppressMessages(library(TCGAbiolinks))

args <- commandArgs(trailingOnly = TRUE)
project <- args[1]
output_file <- args[2]

result <- tryCatch(
  GDCquery_clinic(project = project, type = "clinical"),
  error = function(e) {
    write.csv(data.frame(error = conditionMessage(e)), output_file, row.names = FALSE)
    quit(status = 0)
  }
)

write.csv(result, output_file, row.names = FALSE)
