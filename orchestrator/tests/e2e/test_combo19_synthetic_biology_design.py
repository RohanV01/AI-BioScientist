"""E2E combo 19: synthetic biology design pipeline.

gibson_assembly (real overlap-based assembly of 2 real DNA fragments) ->
dnachisel_optimize (real constraint-based codon optimization of the
exact assembled product). Real hand-off verified by construction: the
two fragments below are two overlapping halves of the same 42bp coding
sequence used in dnachisel_optimize's own tests/test_dnachisel_optimize.py
(ATG start, TGA stop, length a multiple of 3) -- confirmed live before
writing this test that pydna's gibson_assembly reconstructs that exact
42bp sequence as a single linear product from the two halves, which is
then handed to dnachisel_optimize unmodified.

nrpcalc_design is deliberately NOT chained: reading app/tools/nrpcalc_design.py
confirms it does *non-repetitive DNA/RNA part design* (barcodes,
primer-binding sites via combinatorial search over an IUPAC constraint
string) -- not nonribosomal peptide (NRP) synthesis design as the name
might suggest. It shares no real input/output contract with Gibson
assembly or codon optimization (it doesn't take a DNA sequence to
optimize/assemble, it generates a *set* of short non-repetitive parts
from a length/repeat constraint), so it's called here as its own
sub-step on a known-good fixture from its own tests/test_nrpcalc_design.py,
just to genuinely exercise the tool within this same combo file.
"""
import re

import pytest

from app.tools.dnachisel_optimize import optimize_codon_usage
from app.tools.gibson_assembly import simulate_gibson_assembly
from app.tools.nrpcalc_design import design_nonrepetitive_parts
from tests.e2e._utils import E2ERecorder

# Two overlapping halves (15bp overlap) of the exact 42bp coding sequence
# used in tests/test_dnachisel_optimize.py -- ATG start, TGA stop, valid
# E. coli codon-optimization input once reassembled.
CODING_SEQUENCE = "ATGGCTGATAAAGCTGCTGGTATTCATGGTGGCAAGACCTGA"
FRAGMENT_1 = CODING_SEQUENCE[0:30]
FRAGMENT_2 = CODING_SEQUENCE[15:42]

PRODUCT_SEQ_RE = re.compile(r"sequence:\s*([ACGT]+)")


@pytest.mark.e2e
async def test_synthetic_biology_design_pipeline():
    rec = E2ERecorder("synthetic_biology_design_pipeline")

    gibson_text = await rec.call(
        "gibson_assembly.simulate_gibson_assembly",
        simulate_gibson_assembly.handler,
        {"fragments": [FRAGMENT_1, FRAGMENT_2], "min_overlap": 12},
    )
    rec.check(
        "gibson_assembly finds a real 42bp linear product from the two overlapping fragments",
        "42 bp" in gibson_text and "linear" in gibson_text,
        gibson_text[:300],
    )

    match = PRODUCT_SEQ_RE.search(gibson_text)
    assembled_seq = match.group(1) if match else CODING_SEQUENCE
    rec.check(
        "the assembled product's sequence was actually parsed from gibson_assembly's own output "
        "and exactly reconstructs the original 42bp coding sequence -- a genuine hand-off, not a hardcoded fallback",
        match is not None and assembled_seq == CODING_SEQUENCE,
        f"parsed={assembled_seq!r}",
    )

    dnachisel_text = await rec.call(
        "dnachisel_optimize.optimize_codon_usage",
        optimize_codon_usage.handler,
        {"sequence": assembled_seq, "species": "e_coli"},
    )
    rec.check(
        "dnachisel_optimize accepts the exact sequence gibson_assembly produced and returns a valid, translation-preserving codon-optimized sequence",
        "passed: True" in dnachisel_text,
        dnachisel_text[:400],
    )

    # Separate sub-step: nrpcalc_design does unrelated non-repetitive
    # DNA-part design (see module docstring for why it can't chain here).
    nrpcalc_text = await rec.call(
        "nrpcalc_design.design_nonrepetitive_parts",
        design_nonrepetitive_parts.handler,
        {"sequence_constraint": "N" * 16, "max_shared_repeat": 6, "target_size": 3},
    )
    rec.check(
        "nrpcalc_design produces a real 3-part non-repetitive DNA toolbox",
        "[nrpcalc:design]" in nrpcalc_text and "3/3 parts found" in nrpcalc_text,
        nrpcalc_text[:300],
    )

    rec.assert_all_passed()
