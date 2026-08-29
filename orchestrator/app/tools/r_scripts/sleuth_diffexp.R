#!/usr/bin/env Rscript
# Real sleuth differential-expression pipeline (pachterlab/sleuth),
# verbatim the package's own documented workflow
# (sleuth_prep -> sleuth_fit(~condition) -> sleuth_fit(~1) ->
# sleuth_lrt -> sleuth_results). Transcript-to-gene mapping is fetched
# live from Ensembl via biomaRt, same as tximport_summarize.R -- no
# baked-in reference snapshot. Sample-to-condition assignment must
# come from a real uploaded design table -- never fabricated, since
# only the researcher knows which sample belongs to which condition.
# Same Rscript-subprocess pattern as seurat_analyze.R -- see
# app/tools/sleuth_diffexp.py.
#
# Args: <quant_root_dir> <design_tsv> <output_csv>
# design_tsv: two columns, no header -- sample_subdir_name<TAB>condition
# quant_root_dir must contain one Kallisto abundance.h5 subdirectory per sample.
suppressMessages({
  library(sleuth)
  library(biomaRt)
})

args <- commandArgs(trailingOnly = TRUE)
quant_root <- args[1]
design_tsv <- args[2]
output_file <- args[3]

design <- read.delim(design_tsv, header = FALSE, col.names = c("sample", "condition"))
design$path <- file.path(quant_root, design$sample)
missing <- design$sample[!file.exists(file.path(design$path, "abundance.h5"))]
if (length(missing) > 0) {
  stop(sprintf("No abundance.h5 found for sample(s): %s", paste(missing, collapse = ", ")))
}

suppressMessages(library(rhdf5))
tx_ids <- as.character(h5read(file.path(design$path[1], "abundance.h5"), "aux/ids"))
tx_ids_clean <- sub("\\..*$", "", tx_ids)

mart <- useMart("ensembl", dataset = "hsapiens_gene_ensembl")
t2g_raw <- getBM(
  attributes = c("ensembl_transcript_id", "ensembl_gene_id", "hgnc_symbol"),
  filters = "ensembl_transcript_id",
  values = tx_ids_clean,
  mart = mart
)
t2g <- data.frame(
  target_id = tx_ids,
  ens_gene = t2g_raw$ensembl_gene_id[match(tx_ids_clean, t2g_raw$ensembl_transcript_id)],
  ext_gene = t2g_raw$hgnc_symbol[match(tx_ids_clean, t2g_raw$ensembl_transcript_id)]
)

so <- sleuth_prep(design, extra_bootstrap_summary = FALSE, target_mapping = t2g,
                   aggregation_column = "ens_gene", gene_mode = TRUE, transformation_function = function(x) log2(x + 0.5))
so <- sleuth_fit(so, ~condition, "full")
so <- sleuth_fit(so, ~1, "reduced")
so <- sleuth_lrt(so, "reduced", "full")

results <- sleuth_results(so, "reduced:full", test_type = "lrt", show_all = FALSE)
results <- results[order(results$pval), ]
write.csv(results, output_file, row.names = FALSE)
