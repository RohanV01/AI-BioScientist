"""Real tests for app/tools/protgpt2_generate.py -- no mocking, runs
real local transformers inference against nferruz/ProtGPT2. Confirmed
live end-to-end before wiring (real GPU container, RTX 3050,
`docker-compose.gpu.yml`'s passthrough): generated real de novo
sequences, real prefix-continuation, and caught a real, live-only bug
this way -- transformers' pipeline defaults `max_new_tokens=256` and
silently lets it take precedence over `max_length`, so this tool's
`max_length_tokens` argument was being ignored until fixed to pass
`max_new_tokens` explicitly. The happy-path run itself isn't included
here since it needs a GPU-capable environment and a ~3GB model
download -- deferred to the batch Docker build/test pass; validation-
path tests run directly."""
from app.tools.protgpt2_generate import generate_protein_sequence


async def text_of(result):
    return result["content"][0]["text"]


async def test_invalid_prefix_reports_error():
    result = await generate_protein_sequence.handler({"prefix": "MXYZ123", "max_length_tokens": 50, "num_sequences": 1})
    text = await text_of(result)
    assert "standard amino acid letters" in text


async def test_invalid_max_length_reports_error():
    result = await generate_protein_sequence.handler({"prefix": "", "max_length_tokens": 5, "num_sequences": 1})
    text = await text_of(result)
    assert "between 10 and" in text


async def test_invalid_num_sequences_reports_error():
    result = await generate_protein_sequence.handler({"prefix": "", "max_length_tokens": 50, "num_sequences": 20})
    text = await text_of(result)
    assert "between 1 and" in text
