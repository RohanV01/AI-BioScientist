#!/usr/bin/env Rscript
# Real InferCNV pipeline (Bioconductor, broadinstitute/inferCNV),
# verbatim the package's own documented workflow
# (CreateInfercnvObject -> run). InferCNV requires a real gene-order
# file (chromosome/start/end per gene) -- rather than bundling a
# static, staleness-prone gene-position snapshot, this script fetches
# real, current gene coordinates live from Ensembl via biomaRt for
# exactly the genes present in the uploaded matrix, every run. Cell
# group labels (e.g. tumor vs. reference/normal) must come from a real
# uploaded annotations table -- never fabricated. Same
# Rscript-subprocess pattern as seurat_analyze.R -- see
# app/tools/infercnv_analyze.py.
#
# Args: <input_path> <input_type: h5|mtx_dir> <annotations_tsv> <ref_group_names_comma_separated> <output_dir>
suppressMessages({
  library(infercnv)
  library(Seurat)
  library(biomaRt)
})

args <- commandArgs(trailingOnly = TRUE)
input_path <- args[1]
input_type <- args[2]
annotations_tsv <- args[3]
ref_groups <- strsplit(args[4], ",")[[1]]
output_dir <- args[5]

if (input_type == "h5") {
  counts <- Read10X_h5(input_path)
} else {
  counts <- Read10X(data.dir = input_path)
}
if (is.list(counts) && !is.null(counts[["Gene Expression"]])) counts <- counts[["Gene Expression"]]

annotations <- read.delim(annotations_tsv, header = FALSE, row.names = 1)

# Real, live gene-position lookup -- current Ensembl coordinates for
# exactly the genes in this matrix, fetched fresh every run rather
# than from a baked-in reference snapshot.
mart <- useMart("ensembl", dataset = "hsapiens_gene_ensembl")
coords <- getBM(
  attributes = c("hgnc_symbol", "chromosome_name", "start_position", "end_position"),
  filters = "hgnc_symbol",
  values = rownames(counts),
  mart = mart
)
coords <- coords[coords$chromosome_name %in% as.character(c(1:22, "X", "Y")), ]
coords <- coords[!duplicated(coords$hgnc_symbol), ]
coords$chromosome_name <- paste0("chr", coords$chromosome_name)
gene_order <- coords[, c("hgnc_symbol", "chromosome_name", "start_position", "end_position")]
rownames(gene_order) <- gene_order$hgnc_symbol
gene_order$hgnc_symbol <- NULL

infercnv_obj <- CreateInfercnvObject(
  raw_counts_matrix = counts,
  annotations_file = annotations,
  gene_order_file = gene_order,
  ref_group_names = ref_groups
)

dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)
infercnv_obj <- infercnv::run(
  infercnv_obj,
  cutoff = 0.1,
  out_dir = output_dir,
  cluster_by_groups = TRUE,
  denoise = TRUE,
  HMM = FALSE,
  no_plot = TRUE
)
