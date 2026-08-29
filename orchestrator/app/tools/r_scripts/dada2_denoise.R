#!/usr/bin/env Rscript
# Real dada2 amplicon-denoising pipeline (Bioconductor), verbatim the
# package's own documented tutorial workflow (filterAndTrim ->
# learnErrors -> dada -> makeSequenceTable -> removeBimeraDenovo), not
# guessed. Single-end mode -- a real uploaded FASTQ file, not a
# synthetic/paired-only example. Same Rscript-subprocess pattern as
# cluster_profiler_enrich.R -- see app/tools/dada2_denoise.py.
#
# Args: <input_fastq> <output_csv>
suppressMessages(library(dada2))

args <- commandArgs(trailingOnly = TRUE)
input_fastq <- args[1]
output_file <- args[2]

filt_dir <- file.path(dirname(input_fastq), "filtered")
dir.create(filt_dir, showWarnings = FALSE)
filt_path <- file.path(filt_dir, basename(input_fastq))

filterAndTrim(input_fastq, filt_path, truncQ = 2, maxEE = 2, rm.phix = TRUE, compress = TRUE, multithread = TRUE)

errF <- learnErrors(filt_path, multithread = TRUE)
dadaF <- dada(filt_path, err = errF, multithread = TRUE)
seqtab <- makeSequenceTable(dadaF)
seqtab.nochim <- removeBimeraDenovo(seqtab, method = "consensus", multithread = TRUE, verbose = TRUE)

out <- data.frame(
  sequence_variant = colnames(seqtab.nochim),
  abundance = as.integer(seqtab.nochim[1, ])
)
out <- out[order(-out$abundance), ]
write.csv(out, output_file, row.names = FALSE)
