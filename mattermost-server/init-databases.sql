-- Runs once, on first Postgres container init (docker-entrypoint-initdb.d).
-- Creates the two databases this stack needs: one Mattermost owns entirely
-- (its own migrations, never touched by our code), one the Orchestrator
-- Service owns (docs/06-data-model.md schema).

CREATE DATABASE mattermost;
CREATE DATABASE orchestrator;
