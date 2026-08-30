"""E2E combo 20: proteomics and protein design.

proteinmpnn_design (real inverse protein design -- sequences designed to
fold into a real fetched PDB backbone, 1CRN, the same structure
tests/test_proteinmpnn_design.py's own docstring reports a real 0.25s
live GPU run against) is the anchor call. Both other tools are
deliberately separate sub-steps, not chained from it:

- protgpt2_generate (app/tools/protgpt2_generate.py) is unconditional
  de novo generation from the model's own learned distribution (or a
  short amino-acid prefix) -- it is not backbone-conditioned and has no
  way to accept "design a sequence for this exact structure" as input,
  so there is no real hand-off from proteinmpnn's structure-conditioned
  output into it. Confirmed by reading the tool: its only inputs are
  prefix/max_length_tokens/num_sequences.
- mokapot_rescoring (app/tools/mokapot_rescoring.py) rescues PSMs
  (peptide-spectrum matches) from a completely different domain --
  mass-spec database-search output (target/decoy flags + numeric
  search-engine scores per spectrum) -- with no relationship to a
  designed protein sequence, so it's exercised on its own realistic
  synthetic-but-correctly-shaped PSM fixture (same generation approach
  as its own tests/test_mokapot_rescoring.py).

proteinmpnn_design and protgpt2_generate are real local GPU tools (RTX
3050 passthrough on this machine, per project history) -- real model
inference, so these calls may be slow; that's expected, not a bug. Both
tools' own tests/test_*.py note their happy paths are otherwise deferred
to the batch Docker build/test pass (GPU+network dependent).

Confirmed live in this sandbox before writing this test: the `proteinmpnn`
CLI (the `proteinmpnn` PyPI package proteinmpnn_design.py wraps) is not
installed outside the project's Docker image (`pip show proteinmpnn`
reports not found here) -- so the proteinmpnn call below is wrapped to
record an honest, expected FAIL verdict instead of crashing the whole
test if the binary is absent. protgpt2_generate has no such external-
binary dependency (pure transformers/torch, works with or without a
GPU present in this venv) and is exercised for real.
"""
import random

import pytest

from app.tools.mokapot_rescoring import rescore_psms
from app.tools.protgpt2_generate import generate_protein_sequence
from app.tools.proteinmpnn_design import design_sequence_from_structure
from tests.e2e._utils import E2ERecorder

PDB_ID = "1CRN"

random.seed(0)


def _make_psms(n: int = 2000) -> list[dict]:
    psms = []
    for i in range(n):
        is_target = random.random() > 0.5
        score = random.gauss(8, 1.5) if is_target else random.gauss(2, 1.5)
        psms.append(
            {
                "spectrum_id": f"spec{i}",
                "peptide": f"PEPTIDE{i}",
                "is_target": is_target,
                "xcorr": score,
                "mass_error": random.gauss(0, 1),
            }
        )
    return psms


@pytest.mark.e2e
async def test_proteomics_and_protein_design():
    rec = E2ERecorder("proteomics_and_protein_design")

    try:
        mpnn_text = await rec.call(
            "proteinmpnn_design.design_sequence_from_structure",
            design_sequence_from_structure.handler,
            {"pdb_id": PDB_ID, "num_sequences": 2, "sampling_temp": 0.1},
        )
        rec.check(
            "proteinmpnn_design designs real amino-acid sequences for the real fetched 1CRN backbone",
            "[proteinmpnn:design]" in mpnn_text and "score=" in mpnn_text,
            mpnn_text[:400],
        )
    except FileNotFoundError as exc:
        # The `proteinmpnn` CLI is only installed in the project's
        # Docker image, not this bare sandbox (confirmed: `pip show
        # proteinmpnn` reports not found here) -- expected per its own
        # tests/test_proteinmpnn_design.py docstring.
        rec.check("proteinmpnn_design (proteinmpnn CLI not installed in this sandbox -- Docker-only, see tests/test_proteinmpnn_design.py)", False, str(exc))

    # Separate sub-step: unconditional de novo generation, not
    # structure-conditioned -- see module docstring for why this can't
    # genuinely chain from proteinmpnn's output.
    protgpt2_text = await rec.call(
        "protgpt2_generate.generate_protein_sequence",
        generate_protein_sequence.handler,
        {"prefix": "", "max_length_tokens": 50, "num_sequences": 1},
    )
    rec.check(
        "protgpt2_generate produces a real de novo protein sequence",
        "[protgpt2:sequence]" in protgpt2_text,
        protgpt2_text[:300],
    )

    # Separate sub-step: mass-spec PSM rescoring, a different domain
    # entirely -- see module docstring.
    mokapot_text = await rec.call(
        "mokapot_rescoring.rescore_psms",
        rescore_psms.handler,
        {"psms": _make_psms(), "target_fdr": 0.05},
    )
    rec.check(
        "mokapot_rescoring returns real q-value-scored PSMs on a realistic-sized target/decoy set",
        "mokapot PSM rescoring" in mokapot_text and "q-value" in mokapot_text,
        mokapot_text[:300],
    )

    rec.assert_all_passed()
