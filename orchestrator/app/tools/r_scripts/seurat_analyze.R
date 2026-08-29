#!/usr/bin/env Rscript
# Real Seurat scRNA-seq pipeline (CRAN), verbatim the package's own
# canonical tutorial workflow (Read10X/Read10X_h5 -> CreateSeuratObject
# -> NormalizeData -> FindVariableFeatures -> ScaleData -> RunPCA ->
# FindNeighbors -> FindClusters -> RunUMAP -> FindAllMarkers), not
# guessed. Same Rscript-subprocess pattern as cluster_profiler_enrich.R
# -- see app/tools/seurat_analyze.py.
#
# Args: <input_path> <input_type: h5|mtx_dir> <output_clusters_csv> <output_markers_csv>
suppressMessages(library(Seurat))

args <- commandArgs(trailingOnly = TRUE)
input_path <- args[1]
input_type <- args[2]
clusters_out <- args[3]
markers_out <- args[4]

if (input_type == "h5") {
  counts <- Read10X_h5(input_path)
} else {
  counts <- Read10X(data.dir = input_path)
}

# Read10X_h5 can return a list for multi-modal data (e.g. Gene
# Expression + Antibody Capture) -- real CellRanger filtered_feature_bc_matrix.h5
# output shape, take the Gene Expression matrix if so.
if (is.list(counts) && !is.null(counts[["Gene Expression"]])) {
  counts <- counts[["Gene Expression"]]
}

obj <- CreateSeuratObject(counts = counts, project = "openbiolab", min.cells = 3, min.features = 200)
obj <- NormalizeData(obj, verbose = FALSE)
obj <- FindVariableFeatures(obj, selection.method = "vst", nfeatures = 2000, verbose = FALSE)
obj <- ScaleData(obj, verbose = FALSE)
obj <- RunPCA(obj, npcs = min(30, ncol(obj) - 1), verbose = FALSE)
obj <- FindNeighbors(obj, dims = 1:min(10, ncol(obj) - 1), verbose = FALSE)
obj <- FindClusters(obj, resolution = 0.5, verbose = FALSE)

clusters <- data.frame(cell = colnames(obj), cluster = Idents(obj))
write.csv(clusters, clusters_out, row.names = FALSE)

markers <- FindAllMarkers(obj, only.pos = TRUE, min.pct = 0.25, logfc.threshold = 0.25, verbose = FALSE)
write.csv(markers, markers_out, row.names = FALSE)
