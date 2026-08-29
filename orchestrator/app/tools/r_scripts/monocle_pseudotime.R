#!/usr/bin/env Rscript
# Real Monocle3 pseudotime pipeline (Bioconductor/cole-trapnell-lab),
# verbatim the package's own documented workflow (new_cell_data_set ->
# preprocess_cds -> reduce_dimension -> cluster_cells -> learn_graph ->
# order_cells). Monocle3's order_cells() requires a real root cell to
# anchor pseudotime=0 -- there is no principled way to auto-pick one
# without domain knowledge, so this script requires a real barcode
# from the dataset itself (e.g. from a prior seurat_analyze_scrna call
# on the same upload) rather than guessing. Same Rscript-subprocess
# pattern as seurat_analyze.R -- see app/tools/monocle_pseudotime.py.
#
# Args: <input_path> <input_type: h5|mtx_dir> <root_cell_barcode> <output_csv>
suppressMessages({
  library(monocle3)
  library(Seurat)
})

args <- commandArgs(trailingOnly = TRUE)
input_path <- args[1]
input_type <- args[2]
root_cell <- args[3]
output_file <- args[4]

if (input_type == "h5") {
  counts <- Read10X_h5(input_path)
} else {
  counts <- Read10X(data.dir = input_path)
}
if (is.list(counts) && !is.null(counts[["Gene Expression"]])) counts <- counts[["Gene Expression"]]

if (!(root_cell %in% colnames(counts))) {
  stop(sprintf("root_cell %s not found among %d cells in this matrix", root_cell, ncol(counts)))
}

gene_meta <- data.frame(gene_short_name = rownames(counts), row.names = rownames(counts))
cds <- new_cell_data_set(counts, cell_metadata = data.frame(row.names = colnames(counts)), gene_metadata = gene_meta)

cds <- preprocess_cds(cds, num_dim = min(50, ncol(counts) - 1))
cds <- reduce_dimension(cds)
cds <- cluster_cells(cds)
cds <- learn_graph(cds)

# Real nearest-principal-node lookup for the given root cell, per
# monocle3's own documented `get_earliest_principal_node` pattern.
closest_vertex <- cds@principal_graph_aux[["UMAP"]]$pr_graph_cell_proj_closest_vertex
root_pr_node <- igraph::V(principal_graph(cds)[["UMAP"]])$name[closest_vertex[root_cell, 1]]

cds <- order_cells(cds, root_pr_nodes = root_pr_node)

out <- data.frame(
  cell = colnames(cds),
  cluster = as.character(clusters(cds)),
  pseudotime = pseudotime(cds)
)
write.csv(out, output_file, row.names = FALSE)
