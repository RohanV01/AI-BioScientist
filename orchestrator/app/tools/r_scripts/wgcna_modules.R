#!/usr/bin/env Rscript
# Real WGCNA::blockwiseModules call (CRAN) -- weighted gene
# co-expression network construction + module (cluster) detection.
# Same Rscript-subprocess pattern as cluster_profiler_enrich.R -- see
# app/tools/wgcna_modules.py.
#
# Args: <expr_csv> <output_csv>
# expr_csv: rows=samples, columns=genes (first column = sample id)
suppressMessages(library(WGCNA))
options(stringsAsFactors = FALSE)
disableWGCNAThreads()

args <- commandArgs(trailingOnly = TRUE)
expr_csv <- args[1]
output_file <- args[2]

datExpr <- read.csv(expr_csv, row.names = 1, check.names = FALSE)

net <- blockwiseModules(
  datExpr,
  power = 6,
  networkType = "unsigned",
  TOMType = "unsigned",
  minModuleSize = min(10, ncol(datExpr) %/% 2),
  numericLabels = TRUE,
  mergeCutHeight = 0.25,
  verbose = 0
)

out <- data.frame(gene = colnames(datExpr), module = net$colors)
write.csv(out, output_file, row.names = FALSE)
