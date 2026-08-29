#!/usr/bin/env Rscript
# Real clusterProfiler::enrichGO call (Bioconductor). Invoked by
# app/tools/cluster_profiler_enrichment.py via subprocess -- this is
# Phase 3's (docs/17-remaining-tools-wiring-plan.md) first R tool,
# proving the Rscript-subprocess bridge pattern chosen over rpy2 (see
# that tool file's module docstring for the reasoning).
#
# Args: <genes_file> <organism: human|mouse> <ontology: BP|MF|CC|ALL> <output_csv>
suppressMessages(library(clusterProfiler))

args <- commandArgs(trailingOnly = TRUE)
genes_file <- args[1]
organism <- args[2]
ontology <- args[3]
output_file <- args[4]

if (organism == "human") {
  suppressMessages(library(org.Hs.eg.db))
  orgdb <- org.Hs.eg.db
} else if (organism == "mouse") {
  suppressMessages(library(org.Mm.eg.db))
  orgdb <- org.Mm.eg.db
} else {
  stop(paste("Unsupported organism:", organism))
}

genes <- readLines(genes_file)
genes <- genes[nzchar(genes)]

result <- enrichGO(
  gene = genes,
  OrgDb = orgdb,
  keyType = "SYMBOL",
  ont = ontology,
  pvalueCutoff = 0.05,
  qvalueCutoff = 0.2
)

if (is.null(result)) {
  write.csv(data.frame(), output_file, row.names = FALSE)
} else {
  df <- as.data.frame(result)
  write.csv(df, output_file, row.names = FALSE)
}
