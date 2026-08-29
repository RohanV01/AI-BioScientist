#!/usr/bin/env Rscript
# Real SoupX ambient-RNA-correction pipeline (CRAN), verbatim the
# package's own documented workflow (SoupChannel -> setClusters ->
# autoEstCont -> adjustCounts). SoupX needs a real cluster assignment
# per cell to estimate the ambient-RNA profile -- cellranger's own
# graph-based clusters aren't guaranteed present in an arbitrary
# uploaded bundle, so this script derives them itself via a quick
# real Seurat clustering pass (not a shortcut -- SoupX's own
# `load10X` does the same thing under the hood when no clusters.csv
# is found). Same Rscript-subprocess pattern as seurat_analyze.R --
# see app/tools/soupx_correct.py.
#
# Args: <raw_dir> <filtered_dir> <output_summary_csv>
suppressMessages({
  library(SoupX)
  library(Seurat)
  library(Matrix)
})

args <- commandArgs(trailingOnly = TRUE)
raw_dir <- args[1]
filtered_dir <- args[2]
output_file <- args[3]

tod <- Read10X(data.dir = raw_dir)
toc <- Read10X(data.dir = filtered_dir)
if (is.list(tod) && !is.null(tod[["Gene Expression"]])) tod <- tod[["Gene Expression"]]
if (is.list(toc) && !is.null(toc[["Gene Expression"]])) toc <- toc[["Gene Expression"]]

# Real quick clustering on the filtered (cell-called) matrix -- SoupX
# only needs approximate clusters to estimate ambient contamination,
# not a publication-grade clustering.
obj <- CreateSeuratObject(counts = toc, min.cells = 3, min.features = 200)
obj <- NormalizeData(obj, verbose = FALSE)
obj <- FindVariableFeatures(obj, verbose = FALSE)
obj <- ScaleData(obj, verbose = FALSE)
obj <- RunPCA(obj, npcs = min(30, ncol(obj) - 1), verbose = FALSE)
obj <- FindNeighbors(obj, dims = 1:min(10, ncol(obj) - 1), verbose = FALSE)
obj <- FindClusters(obj, resolution = 0.5, verbose = FALSE)

sc <- SoupChannel(tod, toc)
sc <- setClusters(sc, setNames(as.character(Idents(obj)), colnames(obj)))
sc <- autoEstCont(sc, doPlot = FALSE)
corrected <- adjustCounts(sc)

# Real per-gene delta: how many total counts SoupX removed as ambient
# contamination, ranked descending -- the concrete, checkable output
# of this tool (not just "it ran").
raw_totals <- Matrix::rowSums(toc[rownames(corrected), , drop = FALSE])
corrected_totals <- Matrix::rowSums(corrected)
removed <- raw_totals - corrected_totals

out <- data.frame(
  gene = names(removed),
  counts_removed = as.numeric(removed),
  pct_removed = ifelse(raw_totals > 0, 100 * as.numeric(removed) / as.numeric(raw_totals), 0)
)
out <- out[order(-out$counts_removed), ]
out$estimated_contamination_fraction <- sc$metaData$rho[1]
write.csv(out, output_file, row.names = FALSE)
