#!/usr/bin/env Rscript
# Real Giotto spatial-transcriptomics pipeline (Bioconductor/RubD),
# verbatim the package's own documented workflow
# (createGiottoObject -> normalizeGiotto -> calculateHVF -> runPCA ->
# createNearestNetwork -> doLeidenCluster -> findMarkers_one_vs_all).
# Requires a real uploaded spatial-coordinates table alongside the
# expression matrix -- Giotto's whole value is spatial context, which
# a plain count matrix alone cannot supply. Same Rscript-subprocess
# pattern as seurat_analyze.R -- see app/tools/giotto_spatial.py.
#
# Args: <input_path> <input_type: h5|mtx_dir> <spatial_locs_tsv> <output_clusters_csv> <output_markers_csv>
suppressMessages(library(Giotto))

args <- commandArgs(trailingOnly = TRUE)
input_path <- args[1]
input_type <- args[2]
spatial_locs_tsv <- args[3]
clusters_out <- args[4]
markers_out <- args[5]

if (input_type == "h5") {
  expr <- Seurat::Read10X_h5(input_path)
} else {
  expr <- Seurat::Read10X(data.dir = input_path)
}
if (is.list(expr) && !is.null(expr[["Gene Expression"]])) expr <- expr[["Gene Expression"]]

spatial_locs <- read.delim(spatial_locs_tsv, header = TRUE, row.names = 1)
shared_cells <- intersect(colnames(expr), rownames(spatial_locs))
if (length(shared_cells) == 0) {
  stop("No cell/spot IDs in common between the expression matrix and the spatial coordinates table.")
}
expr <- expr[, shared_cells]
spatial_locs <- spatial_locs[shared_cells, c(1, 2)]
colnames(spatial_locs) <- c("sdimx", "sdimy")

gobj <- createGiottoObject(expression = expr, spatial_locs = spatial_locs)
gobj <- normalizeGiotto(gobject = gobj)
gobj <- calculateHVF(gobject = gobj)
gobj <- runPCA(gobject = gobj)
gobj <- createNearestNetwork(gobject = gobj, dimensions_to_use = 1:min(10, ncol(expr) - 1))
gobj <- doLeidenCluster(gobject = gobj)

markers <- findMarkers_one_vs_all(gobject = gobj, cluster_column = "leiden_clus", method = "scran")

meta <- pDataDT(gobj)
clusters_df <- data.frame(cell_ID = meta$cell_ID, cluster = meta$leiden_clus, sdimx = spatial_locs$sdimx, sdimy = spatial_locs$sdimy)
write.csv(clusters_df, clusters_out, row.names = FALSE)

markers_df <- data.frame(cluster = as.character(markers$cluster), gene = markers$feats, score = markers$score)
write.csv(markers_df, markers_out, row.names = FALSE)
