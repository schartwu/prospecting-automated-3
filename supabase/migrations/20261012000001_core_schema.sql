-- Core schema for e-GP Alert v3.
-- Writes come only from the collector (service role, bypasses RLS). RLS is on everywhere with no
-- policies yet, so the public anon key can read nothing until the dashboard adds explicit policies.

-- Departments we query. param says which RSS parameter the code is for.
create table departments (
  code        text primary key,
  param       text not null check (param in ('deptId', 'deptsubId')),
  name        text not null,
  source      text not null default 'v2_list',
  active      boolean not null default true,
  created_at  timestamptz not null default now()
);

-- One row per collector run, for monitoring failures and the 20-item cap.
create table collect_runs (
  id            bigint generated always as identity primary key,
  started_at    timestamptz not null default now(),
  finished_at   timestamptz,
  mode          text not null,
  n_requests    integer not null default 0,
  n_ok          integer not null default 0,
  n_failed      integer not null default 0,
  n_items       integer not null default 0,
  n_new_items   integer not null default 0,
  n_capped      integer not null default 0,
  note          text
);

-- Every RSS item ever seen. The same item reappears for ~1 week, so (announce_type, link) is unique.
create table announcements (
  id             bigint generated always as identity primary key,
  announce_type  text not null check (announce_type in ('P0','15','B0','D0','W0','D1','W1','D2','W2')),
  project_no     text,          -- 11-digit e-GP project number (all types except P0)
  plan_no        text,          -- P... number, P0 only
  method         text,          -- e.g. ประกวดราคาอิเล็กทรอนิกส์ (e-bidding), เฉพาะเจาะจง
  title          text not null,
  link           text not null,
  description    text,
  pub_date       date,
  dept_code      text,          -- code we queried; not a FK because nationwide queries have none
  dept_name      text,
  first_seen_run bigint references collect_runs (id) on delete set null,
  first_seen_at  timestamptz not null default now(),
  last_seen_at   timestamptz not null default now(),
  raw            jsonb not null default '{}'::jsonb,
  unique (announce_type, link)
);
create index announcements_project_no_idx on announcements (project_no) where project_no is not null;
create index announcements_pub_date_idx on announcements (pub_date desc);
create index announcements_first_seen_run_idx on announcements (first_seen_run);
create index announcements_dept_code_idx on announcements (dept_code);

-- Data pulled from the announcement PDF (budget, bid date, ...). One row per announcement.
create table announcement_details (
  announcement_id  bigint primary key references announcements (id) on delete cascade,
  budget_thb       numeric(15,2),
  bid_date         date,
  item_count       integer,
  extracted        jsonb not null default '{}'::jsonb,
  error            text,
  extracted_at     timestamptz not null default now()
);

-- Relevance to OfficeMate, from rules + Gemini. One current row per announcement.
create table classifications (
  announcement_id  bigint primary key references announcements (id) on delete cascade,
  relevant         boolean not null,
  score            smallint not null check (score between 0 and 100),
  category         text,          -- OfficeMate category, e.g. 'IT', 'Office supplies', 'Furniture'
  reason           text,
  model            text not null, -- 'rules-v1', 'gemini-...'
  classified_at    timestamptz not null default now()
);
create index classifications_relevant_idx on classifications (score desc) where relevant;

-- Sales feedback and outcomes per project (or per P0 plan, which has no project_no).
create table feedback (
  id               bigint generated always as identity primary key,
  announcement_id  bigint not null references announcements (id) on delete cascade,
  status           text not null check (status in ('relevant','not_relevant','preparing','bid','won','lost')),
  amount_thb       numeric(15,2),
  note             text,
  created_by       text,
  created_at       timestamptz not null default now()
);
create index feedback_announcement_id_idx on feedback (announcement_id);

alter table departments           enable row level security;
alter table collect_runs          enable row level security;
alter table announcements         enable row level security;
alter table announcement_details  enable row level security;
alter table classifications       enable row level security;
alter table feedback              enable row level security;
