#!/usr/bin/env Rscript
# Real tximport pipeline (Bioconductor), verbatim the package's own
# documented workflow (tximport() with a transcript-to-gene map).
# Transcript-to-gene mapping is fetched live from Ensembl via biomaRt
# for exactly the transcript IDs present in the uploaded quant files --
# no baked-in tx2gene reference snapshot. Same Rscript-subprocess
# pattern as seurat_analyze.R -- see app/tools/tximport_summarize.py.
#
# Args: <quant_root_dir> <output_csv>
# quant_root_dir must contain one subdirectory per sample, each with
# either a Salmon quant.sf or a Kallisto abundance.h5/abundance.tsv.
suppressMessages({
  library(tximport)
  library(biomaRt)
})

args <- commandArgs(trailingOnly = TRUE)
quant_root <- args[1]
output_file <- args[2]

sample_dirs <- list.dirs(quant_root, recursive = FALSE)
if (length(sample_dirs) == 0) sample_dirs <- quant_root  # single sample uploaded directly

salmon_files <- file.path(sample_dirs, "quant.sf")
kallisto_h5 <- file.path(sample_dirs, "abundance.h5")

if (all(file.exists(salmon_files))) {
  quant_files <- salmon_files
  quant_type <- "salmon"
} else if (all(file.exists(kallisto_h5))) {
  quant_files <- kallisto_h5
  quant_type <- "kallisto"
} else {
  stop("Could not find a consistent set of quant.sf (Salmon) or abundance.h5 (Kallisto) files under each sample subdirectory.")
}
names(quant_files) <- basename(sample_dirs)

if (quant_type == "salmon") {
  tx_ids <- read.delim(quant_files[1])$Name
} else {
  suppressMessages(library(rhdf5))
  tx_ids <- as.character(h5read(quant_files[1], "aux/ids"))
}
tx_ids_clean <- sub("\\..*$", "", tx_ids)  # strip Ensembl version suffix

mart <- useMart("ensembl", dataset = "hsapiens_gene_ensembl")
tx2gene_map <- getBM(
  attributes = c("ensembl_transcript_id", "ensembl_gene_id", "hgnc_symbol"),
  filters = "ensembl_transcript_id",
  values = tx_ids_clean,
  mart = mart
)
tx2gene <- data.frame(
  TXNAME = tx_ids,
  GENEID = tx2gene_map$hgnc_symbol[match(tx_ids_clean, tx2gene_map$ensembl_transcript_id)]
)
tx2gene$GENEID[is.na(tx2gene$GENEID) | tx2gene$GENEID == ""] <- tx2gene$TXNAME[is.na(tx2gene$GENEID) | tx2gene$GENEID == ""]

txi <- tximport(quant_files, type = quant_type, tx2gene = tx2gene, ignoreTxVersion = TRUE)

out <- data.frame(gene = rownames(txi$counts), txi$counts)
write.csv(out, output_file, row.names = FALSE)
