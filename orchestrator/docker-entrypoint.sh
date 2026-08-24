#!/bin/sh
set -e
# Real gap found by the from-scratch clean-clone verification pass: a
# genuinely fresh Postgres volume has no schema at all (no alembic history
# table, no "org"/"agent"/... tables) -- nothing ever ran migrations
# automatically, and README.md never documented a manual `alembic upgrade
# head` step either. scripts/seed_dev_data.py crashed on its very first
# query (UndefinedTableError: relation "org" does not exist) on a real
# fresh clone, before this fix. Running the migration here, on every
# container start, closes this permanently rather than adding one more
# manual step someone can forget -- alembic upgrade head is a no-op when
# already at head, so this is safe on every restart, not just the first.
alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
