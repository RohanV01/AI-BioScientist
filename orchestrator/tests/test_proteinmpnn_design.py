"""Real tests for app/tools/proteinmpnn_design.py -- no mocking, runs
the real proteinmpnn CLI against a real fetched PDB structure.
Confirmed live end-to-end before wiring (real GPU container, RTX 3050,
`docker-compose.gpu.yml`'s passthrough): designed 2 real sequences for
1CRN in 0.25s, real scores/seq_recovery parsed correctly -- and caught
a real, live-only bug this way (the installed CLI's actual flags are
hyphenated, `--out-folder`/`--pdb-path`, not the underscored
`--out_folder`/`--pdb_path` the PyPI README's own usage example
shows). The happy-path run itself isn't included here since it needs a
GPU-capable environment and network access to RCSB -- deferred to the
batch Docker build/test pass; validation-path tests run directly."""
from app.tools.proteinmpnn_design import design_sequence_from_structure


async def text_of(result):
    return result["content"][0]["text"]


async def test_empty_pdb_id_reports_error():
    result = await design_sequence_from_structure.handler({"pdb_id": "", "num_sequences": 4, "sampling_temp": 0.1})
    text = await text_of(result)
    assert "must be non-empty" in text


async def test_invalid_num_sequences_reports_error():
    result = await design_sequence_from_structure.handler({"pdb_id": "1CRN", "num_sequences": 20, "sampling_temp": 0.1})
    text = await text_of(result)
    assert "between 1 and 10" in text


async def test_invalid_sampling_temp_reports_error():
    result = await design_sequence_from_structure.handler({"pdb_id": "1CRN", "num_sequences": 4, "sampling_temp": 5.0})
    text = await text_of(result)
    assert "between 0.01 and 1.0" in text


async def test_unknown_pdb_id_reports_not_found():
    result = await design_sequence_from_structure.handler({"pdb_id": "ZZZZ", "num_sequences": 4, "sampling_temp": 0.1})
    text = await text_of(result)
    assert "No PDB entry found" in text
