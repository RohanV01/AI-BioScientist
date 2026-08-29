#!/usr/bin/env Rscript
# Real poolfstat::computeFST call (CRAN). Same Rscript-subprocess
# pattern as cluster_profiler_enrich.R -- see
# app/tools/poolfstat_fst.py for the wrapper.
#
# Args: <counts_csv> <output_csv>
# counts_csv columns: population,snp,ref_count,total_count (long format)
suppressMessages(library(poolfstat))

args <- commandArgs(trailingOnly = TRUE)
counts_csv <- args[1]
output_file <- args[2]

df <- read.csv(counts_csv, stringsAsFactors = FALSE)
pops <- unique(df$population)
snps <- unique(df$snp)
npops <- length(pops)
nsnp <- length(snps)

refmat <- matrix(0L, nrow = nsnp, ncol = npops)
totmat <- matrix(0L, nrow = nsnp, ncol = npops)
pop_idx <- setNames(seq_along(pops), pops)
snp_idx <- setNames(seq_along(snps), snps)

for (i in seq_len(nrow(df))) {
  r <- snp_idx[[df$snp[i]]]
  c <- pop_idx[[df$population[i]]]
  refmat[r, c] <- df$ref_count[i]
  totmat[r, c] <- df$total_count[i]
}

snp.info <- data.frame(
  Chromosome = rep("1", nsnp),
  Position = seq_len(nsnp),
  RefAllele = rep("A", nsnp),
  AltAllele = rep("T", nsnp)
)

cd <- new(
  "countdata",
  npops = npops,
  nsnp = nsnp,
  refallele.count = refmat,
  total.count = totmat,
  snp.info = snp.info,
  popnames = pops
)

res <- computeFST(cd, verbose = FALSE)

out <- data.frame(
  metric = c("FST_estimate", "FST_blockjackknife_mean", "FST_se", "FST_ci_lower", "FST_ci_upper"),
  value = res$FST
)
write.csv(out, output_file, row.names = FALSE)
