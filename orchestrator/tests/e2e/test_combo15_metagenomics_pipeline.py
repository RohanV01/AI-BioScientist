"""E2E combo 15 (metagenomics/microbial-genomics cluster -- no combo
previously covered this cluster at all): metagenomic-sample-to-annotation
pipeline.

kraken2_classify / kaiju_classify (taxonomic classification of sample
reads) -> prodigal_genes (ab initio gene prediction on an assembled
genome) -> prokka_annotate / bakta_annotate (whole-genome functional
annotation) -> barrnap_rrna (rRNA gene prediction) -> checkm2_quality /
checkv_quality (genome/viral-genome completeness QC) ->
amrfinder_resistance (AMR gene detection, fed the real protein sequence
prodigal_genes just predicted -- a genuine hand-off) ->
fastani_similarity (whole-genome ANI vs a near-identical reference) ->
blast_search / diamond_search (sequence search, again fed prodigal's
real predicted protein -- another genuine hand-off).

Real, live handler calls, no mocking -- same pattern as the other
tests/e2e/test_comboN_*.py files (see test_combo1_target_validation.py,
this file's exact template).

All twelve of these tools are subprocess-wrapped compiled bioinformatics
binaries (kraken2, kaiju, prokka, bakta, barrnap, prodigal, checkm2,
checkv, amrfinder, fastANI, blastn/makeblastdb, diamond) -- confirmed
live here that none of apt/pip/static-binary installs, nor the
Docker-image-baked reference databases (kraken2's k2_viral, kaiju's
kaiju_db_viruses, checkm2's/checkv's DIAMOND/reference DBs), are present
in this bare dev sandbox, so every one of these calls raises a real
FileNotFoundError out of subprocess.run() before the handler can even
run its own logic. Per each tool's own tests/test_<name>.py docstring,
these happy-path runs are "not locally testable in this sandbox ...
deferred to the batch Docker build/test pass" -- this combo still makes
every real handler call (so the chain is correct and ready once run in
Docker/CI, where prodigal/barrnap/fastANI/blastn/diamond in particular
already have real happy-path fixtures wired in below, lifted straight
from their own tests/test_<name>.py files) and uses a local
_call_tolerant() wrapper (below) to record a missing-binary
FileNotFoundError as a normal failed rec.check() rather than letting it
crash the whole pipeline -- the same tolerance the task's own
instructions extend to a slow/rate-limited live API.
"""
import re

import pytest

from app.tools.amrfinder_resistance import detect_resistance_genes
from app.tools.bakta_annotate import annotate_genome_bakta
from app.tools.barrnap_rrna import predict_rrna_genes
from app.tools.blast_search import blast_search
from app.tools.checkm2_quality import assess_genome_quality
from app.tools.checkv_quality import assess_viral_genome_quality
from app.tools.diamond_search import diamond_search
from app.tools.fastani_similarity import compute_genome_ani
from app.tools.kaiju_classify import classify_sequence_kaiju
from app.tools.kraken2_classify import classify_sequence_kraken2
from app.tools.prodigal_genes import predict_genes
from app.tools.prokka_annotate import annotate_genome_prokka
from tests.e2e._utils import E2ERecorder

PROTEIN_RE = re.compile(r"protein: ([A-Z\*]+)")


async def _call_tolerant(rec: E2ERecorder, label: str, handler, args: dict) -> str:
    """Same as rec.call(), except a missing compiled binary (this sandbox
    was never meant to have kraken2/kaiju/prokka/bakta/checkm2/checkv/
    amrfinder/fastANI/blastn/diamond installed -- see module docstring)
    raises FileNotFoundError straight out of subprocess.run() before the
    tool's own handler gets a chance to turn it into a text response.
    That's a real, expected environment gap here, not a hand-off bug --
    recorded as a normal (False) check, same tolerance the task's own
    instructions give a slow/rate-limited live API, rather than left to
    crash the whole combo (which would also swallow every later step)."""
    try:
        return await rec.call(label, handler, args)
    except FileNotFoundError as exc:
        rec.check(f"{label} ran (binary available in this environment)", False, f"binary not installed in this sandbox: {exc}")
        return ""


def _random_seq(n: int, seed: int) -> str:
    import random

    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(n))


def _mutate(seq: str, n_mutations: int, seed: int) -> str:
    import random

    rng = random.Random(seed)
    chars = list(seq)
    for i in rng.sample(range(len(chars)), n_mutations):
        chars[i] = rng.choice("ACGT")
    return "".join(chars)


# A real E. coli lacZ gene fragment -- the same known-good fixture
# tests/test_prodigal_genes.py uses for its real happy-path gene-calling
# run, and long enough (>=200bp) to double as a genome/contig input for
# prokka_annotate/bakta_annotate/barrnap_rrna.
LACZ_FRAGMENT = (
    "ATGACCATGATTACGGATTCACTGGCCGTCGTTTTACAACGTCGTGACTGGGAAAACCCTGGCGTTACCCAACTTAATCGCCTTGCAGCACATCCCCCTTTCGCCAGCTGGCGTAATAGCGAAGAGGCCCGCACCGATCGCCCTTCCCAACAGTTGCGCAGCCTGAATGGCGAATGGCGCCTGATGCGGTATTTTCTCCTTACGCATCTGTGCGGTATTTCACACCGCATATGGTGCACTCTCAGTACAATCTGCTCTGATGCCGCATAGTTAAGCCAGCCCCGACACCCGCCAACACCCGCTGACGCGCCCTGACGGGCTTGTCTGCTCCCGGCATCCGCTTACAGACAAGCTGTGACCGTCTCCGGGAGCTGCATGTGTCAGAGGTTTTCACCGTCATCACCGAAACGCGCGAGACGAAAGGGCCTCGTGATACGCCTATTTTTATAGGTTAATGTCATGATAATAATGGTTTCTTAGACGTCAGGTGGCACTTTTCGGGGAAATGTGCGCGGAACCCCTATTTGTTTATTTTTCTAAATACATTCAAATATGTATCCGCTCATGAGACAATAACCCTGATAAATGCTTCAATAATATTGAAAAAGGAAGAGTATGAGTATTCAACATTTCCGTGTCGCCCTTATTCCCTTTTTTGCGGCATTTTGCCTTCCTGTTTTTGCTCACCCAGAAACGCTGGTGAAAGTAAAAGATGCTGAAGATCAGTTGGGTGCACGAGTGGGTTACATCGAACTGGATCTCAACAGCGGTAAGATCCTTGAGAGTTTTCGCCCCGAAGAACGTTTTCCAATGATGAGCACTTTTAAAGTTCTGCTATGTGGCGCGGTATTATCCCGTATTGACGCCGGGCAAGAGCAACTCGGTCGCCGCATACACTATTCTCAGAATGACTTGGTTGAGTACTCACCAGTCACAGAAAAGCATCTTACGGATGGCATGACAGTAAGAGAATTATGCAGTGCTGCCATAACCATGAGTGATAACACTGCGGCCAACTTACTTCTGACAACGATCGGAGGACCGAAGGAGCTAACCGCTTTTTTGCACAACATGGGGGATCATGTAACTCGCCTTGATCGTTGGGAACCGGAGCTGAATGAAGCCATACCAAACGACGAGCGTGACACCACGATGCCTGTAGCAATGGCAACAACGTTGCGCAAACTATTAACTGGCGAACTACTTACTCTAGCTTCCCGGCAACAATTAATAGACTGGATGGAGGCGGATAAAGTTGCAGGACCACTTCTGCGCTCGGCCCTTCCGGCTGGCTGGTTTATTGCTGATAAATCTGGAGCCGGTGAGCGTGGGTCTCGCGGTATCATTGCAGCACTGGGGCCAGATGGTAAGCCCTCCCGTATCGTAGTTATCTACACGACGGGGAGTCAGGCAACTATGGATGAACGAAATAGACAGATCGCTGAGATAGGTGCCTCACTGATTAAGCATTGGTAACTGTCAGACCAAGTTTACTCATATATACTTTAGATTGATTTAAAACTTCATTTTTAATTTAAAAGGATCTAGGTGAAGATCCTTTTTGATAATCTCATGACCAAAATCCCTTAACGTGAGTTTTCGTTCCACTGAGCGTCAGACCCC"
)

# A real partial 16S rRNA sequence -- the same known-good fixture
# tests/test_barrnap_rrna.py uses for its real happy-path detection run.
REAL_PARTIAL_16S = (
    "AGAGTTTGATCCTGGCTCAGATTGAACGCTGGCGGCAGGCCTAACACATGCAAGTCGAACGGTAACAGGAAGAAGCTTGCTTCTTTGCTGACGAGTGGC"
    "GGACGGGTGAGTAATGTCTGGGAAACTGCCTGATGGAGGGGGATAACTACTGGAAACGGTAGCTAATACCGCATAACGTCGCAAGACCAAAGAGGGGGA"
    "CCTTCGGGCCTCTTGCCATCGGATGTGCCCAGATGGGATTAGCTAGTAGGTGGGGTAACGGCTCACCTAGGCGACGATCCCTAGCTGGTCTGAGAGGAT"
    "GACCAGCCACACTGGAACTGAGACACGGTCCAGACTCCTACGGGAGGCAGCAGTGGGGAATATTGCACAATGGGCGCAAGCCTGATGCAGCCATGCCGC"
    "GTGTATGAAGAAGGCCTTCGGGTTGTAAAGTACTTTCAGCGGGGAGGAAGGGAGTAAAGTTAATACCTTTGCTCATTGACGTTACCCGCAGAAGAAGCA"
    "CCGGCTAACTCCGTGCCAGCAGCCGCGGTAATACGGAGGGTGCAAGCGTTAATCGGAATTACTGGGCGTAAAGCGCACGCAGGCGGTTTGTTAAGTCAG"
    "ATGTGAAATCCCCGGGCTCAACCTGGGAACTGCATCTGATACTGGCAAGCTTGAGTCTCGTAGAGGGGGGTAGAATTCCAGGTGTAGCGGTGAAATGCG"
    "TAGAGATCTGGAGGAATACCGGTGGCGAAGGCGGCCCCCTGGACGAAGACTGACGCTCAGGTGCGAAAGCGTGGGGAGCAAACAGG"
)

# Genome-scale sequences (>=20000bp, FastANI's own confirmed-live floor)
# for the ANI hand-off and (>=5000bp) for the CheckM2 completeness QC --
# same random-sequence + point-mutation fixture pattern
# tests/test_fastani_similarity.py itself uses for its real happy-path run.
GENOME_SEQ = _random_seq(25000, 42)
GENOME_SEQ_MUTATED = _mutate(GENOME_SEQ, 250, 43)


@pytest.mark.e2e
async def test_metagenomics_pipeline():
    rec = E2ERecorder("metagenomics_pipeline")

    # 1. Taxonomic classification of a sample/read sequence -- two
    # independent methods (exact k-mer vs protein-level translated
    # alignment) against real (virus-scoped) reference databases.
    kraken2_text = await _call_tolerant(
        rec, "kraken2_classify.classify_sequence_kraken2", classify_sequence_kraken2.handler, {"sequence": LACZ_FRAGMENT[:500]}
    )
    if kraken2_text:
        rec.check(
            "kraken2 handler ran and returned a classification or a well-formed 'no match' response",
            "Kraken2" in kraken2_text,
            kraken2_text[:200],
        )

    kaiju_text = await _call_tolerant(
        rec, "kaiju_classify.classify_sequence_kaiju", classify_sequence_kaiju.handler, {"sequence": LACZ_FRAGMENT[:500]}
    )
    if kaiju_text:
        rec.check(
            "kaiju handler ran and returned a classification or a well-formed 'no match'/failure response",
            bool(kaiju_text.strip()),
            kaiju_text[:200],
        )

    # 2. Ab initio gene prediction on an assembled genome/contig --
    # produces real predicted protein sequences used downstream.
    prodigal_text = await _call_tolerant(rec, "prodigal_genes.predict_genes", predict_genes.handler, {"sequence": LACZ_FRAGMENT})
    predicted_proteins = PROTEIN_RE.findall(prodigal_text)
    rec.check(
        "prodigal predicted at least one real protein-coding gene from the genome fragment",
        bool(predicted_proteins),
        prodigal_text[:200],
    )
    # Fall back to a real fixture protein (diamond_search's own
    # known-good query) only if prodigal's real gene calling produced
    # nothing, so the downstream hand-off checks still exercise real
    # handler calls end to end.
    predicted_protein = (
        predicted_proteins[0].rstrip("*")
        if predicted_proteins
        else "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"
    )

    # 3. Whole-genome functional annotation -- two alternative pipelines
    # on the same genome fragment prodigal just called genes on.
    prokka_text = await _call_tolerant(rec, "prokka_annotate.annotate_genome_prokka", annotate_genome_prokka.handler, {"sequence": LACZ_FRAGMENT})
    if prokka_text:
        rec.check("prokka handler ran and returned an annotation or well-formed failure", bool(prokka_text.strip()), prokka_text[:200])

    bakta_text = await _call_tolerant(rec, "bakta_annotate.annotate_genome_bakta", annotate_genome_bakta.handler, {"sequence": LACZ_FRAGMENT})
    if bakta_text:
        rec.check("bakta handler ran and returned an annotation or well-formed failure", bool(bakta_text.strip()), bakta_text[:200])

    # 4. rRNA gene prediction -- real local run against a real partial
    # 16S sequence (the standard marker gene, not naturally present in
    # the lacZ protein-coding fragment above, so a separate real
    # known-good fixture is used here).
    barrnap_text = await _call_tolerant(
        rec, "barrnap_rrna.predict_rrna_genes", predict_rrna_genes.handler, {"sequence": REAL_PARTIAL_16S, "kingdom": "bac"}
    )
    if barrnap_text:
        rec.check(
            "barrnap detected the real 16S rRNA gene in the known-good fixture sequence",
            "16S_rRNA" in barrnap_text,
            barrnap_text[:200],
        )

    # 5. Completeness/contamination QC -- prokaryotic genome bin (CheckM2)
    # and viral contig (CheckV), against their real reference databases.
    checkm2_text = await _call_tolerant(rec, "checkm2_quality.assess_genome_quality", assess_genome_quality.handler, {"sequence": GENOME_SEQ})
    if checkm2_text:
        rec.check("checkm2 handler ran and returned a quality report or well-formed failure", bool(checkm2_text.strip()), checkm2_text[:200])

    checkv_text = await _call_tolerant(
        rec, "checkv_quality.assess_viral_genome_quality", assess_viral_genome_quality.handler, {"sequence": REAL_PARTIAL_16S}
    )
    if checkv_text:
        rec.check("checkv handler ran and returned a quality report or well-formed failure", bool(checkv_text.strip()), checkv_text[:200])

    # 6. AMR gene detection -- fed the real predicted protein sequence
    # from prodigal_genes above (genuine hand-off: an annotated genome's
    # predicted protein feeding directly into AMR gene finding).
    amrfinder_text = await _call_tolerant(
        rec,
        "amrfinder_resistance.detect_resistance_genes",
        detect_resistance_genes.handler,
        {"sequence": predicted_protein, "is_nucleotide": False},
    )
    if amrfinder_text:
        rec.check(
            "amrfinder accepted prodigal's real predicted protein as valid protein input (no invalid-character rejection)",
            "invalid" not in amrfinder_text.lower(),
            amrfinder_text[:200],
        )

    # 7. Whole-genome ANI vs a near-identical reference -- real local run.
    fastani_text = await _call_tolerant(
        rec,
        "fastani_similarity.compute_genome_ani",
        compute_genome_ani.handler,
        {"query_sequence": GENOME_SEQ, "reference_sequence": GENOME_SEQ_MUTATED},
    )
    if fastani_text:
        rec.check(
            "fastani computed a real ANI value between the genome and its near-identical mutated copy",
            "FastANI" in fastani_text and "%" in fastani_text,
            fastani_text[:200],
        )

    # 8. Sequence search on the predicted protein -- again a genuine
    # hand-off from prodigal_genes, this time into two search engines.
    blast_text = await _call_tolerant(
        rec,
        "blast_search.blast_search",
        blast_search.handler,
        {
            "query_sequence": predicted_protein,
            "reference_sequences": {"self_match": predicted_protein, "unrelated": "GGGGWWWWKKKKPPPPLLLLIIIIVVVVFFFFYYYYNNNNQQQQSSSSTTTTCCCC"},
            "sequence_type": "prot",
        },
    )
    if blast_text:
        rec.check(
            "blast_search found prodigal's real predicted protein as an exact self-match reference (real hand-off)",
            "self_match" in blast_text and ("100.0" in blast_text or "100.00" in blast_text),
            blast_text[:200],
        )

    diamond_text = await _call_tolerant(
        rec,
        "diamond_search.diamond_search",
        diamond_search.handler,
        {
            "query_sequence": predicted_protein,
            "reference_sequences": {"self_match": predicted_protein, "unrelated": "GGGGWWWWKKKKPPPPLLLLIIIIVVVVFFFFYYYYNNNNQQQQSSSSTTTTCCCC"},
        },
    )
    if diamond_text:
        rec.check(
            "diamond_search found prodigal's real predicted protein as an exact self-match reference (real hand-off)",
            "self_match" in diamond_text,
            diamond_text[:200],
        )

    rec.assert_all_passed()
