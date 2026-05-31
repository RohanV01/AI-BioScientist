"""
Quick smoke test: run Phase 0 locally without Celery.
Usage: python scripts/dry_run.py --disease "pancreatic cancer"
"""
import argparse
import json
import sys
import logging
from pathlib import Path

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from src.config.run_config import RunConfig
from src.phases.phase0.runner import run_phase0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--disease", default="pancreatic cancer")
    parser.add_argument("--provider", default="lmstudio", choices=["lmstudio", "anthropic", "openai"])
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    config = RunConfig(
        disease_name=args.disease,
        dry_run=args.dry_run,
        llm={"provider": args.provider},
    )

    print(f"\n=== Phase 0 dry run: '{args.disease}' ===\n")
    result = run_phase0(run_id="local-test", config=config, db=None)
    print(json.dumps(result, indent=2, default=str))

    verdict = result.get("go_no_go", "unknown")
    missing = result.get("missing_required", [])
    print(f"\nVerdict: {verdict}")
    if missing:
        print(f"Missing: {missing}")


if __name__ == "__main__":
    main()
