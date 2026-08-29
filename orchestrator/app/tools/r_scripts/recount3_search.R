#!/usr/bin/env Rscript
# Real recount3::available_projects call (Bioconductor) -- fetches
# recount3's real public RNA-seq study catalog (project, organism,
# file_source, n_samples), no expression-matrix download. Same
# Rscript-subprocess pattern as cluster_profiler_enrich.R -- see
# app/tools/recount3_search.py.
#
# Args: <organism: human|mouse> <output_csv>
suppressMessages(library(recount3))

args <- commandArgs(trailingOnly = TRUE)
organism <- args[1]
output_file <- args[2]

result <- available_projects(organism = organism)
write.csv(result, output_file, row.names = FALSE)
