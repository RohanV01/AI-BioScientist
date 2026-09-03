"""Cross-experiment Memory layer (docs/18-platform-capability-gaps.md Pass 1
#1), inspired by (not built on) github.com/rohitg00/agentmemory's tiered-
consolidation/hybrid-retrieval design -- see the multi-stage research
pipeline plan section 3 for the full mapping and what was deliberately not
adopted (its separate runtime, and its decay/TTL forgetting-curve model).

- consolidate.py: write path -- extracts MemoryFact rows from a Response.
- retrieve.py: read path -- hybrid BM25+vector+entity retrieval with RRF
  fusion.
"""
