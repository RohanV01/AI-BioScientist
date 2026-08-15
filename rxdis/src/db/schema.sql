-- Supabase schema — run once via the SQL editor or `psql`.
-- Matches Master PRD §4 exactly.

-- ── Core tables ─────────────────────────────────────────────────────────────

create table if not exists profiles (
  id          uuid primary key references auth.users(id),
  email       text not null,
  org         text,
  created_at  timestamptz default now()
);

create table if not exists projects (
  id          uuid primary key default gen_random_uuid(),
  owner_id    uuid not null references profiles(id),
  name        text not null,
  created_at  timestamptz default now()
);

create table if not exists runs (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid not null references projects(id),
  owner_id        uuid not null references profiles(id),
  disease_name    text not null,
  efo_id          text,
  config          jsonb not null,
  status          text not null default 'pending',
  current_phase   int  not null default 0,
  intent_mode     text not null,
  dry_run         boolean not null default false,
  cost_estimate   numeric,
  cost_actual     numeric default 0,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

create table if not exists phase_results (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  phase           int  not null,
  status          text not null default 'pending',
  input_json      jsonb,
  output_json     jsonb,
  artifact_paths  text[],
  started_at      timestamptz,
  finished_at     timestamptz,
  error           text,
  unique(run_id, phase)
);

create table if not exists targets (
  id               uuid primary key default gen_random_uuid(),
  run_id           uuid not null references runs(id) on delete cascade,
  rank             int,
  ensembl_id       text,
  symbol           text,
  aggregate_score  numeric,
  validation_score numeric,
  tdl              text,
  modality_primary text,
  modality_secondary text,
  seeded           boolean default false,
  evidence_trail   jsonb,
  created_at       timestamptz default now()
);

create table if not exists candidates (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  -- Gene symbol (e.g. 'KRAS'), NOT a FK to targets.id. The pipeline keys
  -- candidates by symbol; see src/db/run_state.insert_candidate().
  target_id       text,
  kind            text not null,
  identifier      text,
  smiles          text,
  sequence        text,
  combined_score  numeric,
  subscores       jsonb,
  artifact_paths  text[],
  created_at      timestamptz default now()
);

create table if not exists decisions (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  phase           int  not null,
  gate            text not null,
  llm_provider    text not null,
  llm_model       text not null,
  prompt          text,
  raw_response    text,
  decision_json   jsonb,
  human_override  jsonb,
  created_at      timestamptz default now()
);

create table if not exists compute_log (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  phase           int,
  step            text,
  service         text,
  cost_usd        numeric default 0,
  wall_time_s     numeric,
  created_at      timestamptz default now()
);

create table if not exists llm_chunks (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  task            text not null,
  chunk_index     int  not null,
  total_chunks    int  not null,
  input_ref       text,
  output_json     jsonb,
  status          text not null default 'pending',
  created_at      timestamptz default now(),
  unique(run_id, task, chunk_index)
);

create table if not exists user_llm_credentials (
  id            uuid primary key default gen_random_uuid(),
  owner_id      uuid not null references profiles(id),
  provider      text not null,
  enc_api_key   text,
  base_url      text,
  default_model text,
  created_at    timestamptz default now(),
  unique(owner_id, provider)
);

-- ── Row-Level Security ────────────────────────────────────────────────────────

alter table projects         enable row level security;
alter table runs             enable row level security;
alter table phase_results    enable row level security;
alter table targets          enable row level security;
alter table candidates       enable row level security;
alter table decisions        enable row level security;
alter table compute_log      enable row level security;
alter table llm_chunks       enable row level security;
alter table user_llm_credentials enable row level security;

-- Users see only their own rows
create policy "owner_only" on projects         using (owner_id = auth.uid());
create policy "owner_only" on runs             using (owner_id = auth.uid());
create policy "owner_only" on phase_results    using (run_id in (select id from runs where owner_id = auth.uid()));
create policy "owner_only" on targets          using (run_id in (select id from runs where owner_id = auth.uid()));
create policy "owner_only" on candidates       using (run_id in (select id from runs where owner_id = auth.uid()));
create policy "owner_only" on decisions        using (run_id in (select id from runs where owner_id = auth.uid()));
create policy "owner_only" on compute_log      using (run_id in (select id from runs where owner_id = auth.uid()));
create policy "owner_only" on llm_chunks       using (run_id in (select id from runs where owner_id = auth.uid()));
create policy "owner_only" on user_llm_credentials using (owner_id = auth.uid());
