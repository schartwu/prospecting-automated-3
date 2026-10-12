-- Gemini requests per model per quota day. Free-tier daily quotas reset at midnight Pacific time,
-- so the day is counted in America/Los_Angeles.
create table ai_usage (
  day       date not null,
  model     text not null,
  requests  integer not null default 0,
  primary key (day, model)
);
alter table ai_usage enable row level security;

-- Atomically reserve one request for p_model if it is still under p_budget today. Returns false when
-- the budget is used up, so the caller moves on to the next model instead of hitting the hard limit.
create or replace function ai_take(p_model text, p_budget integer)
returns boolean
language plpgsql
set search_path = ''
as $$
declare
  v_day date := (now() at time zone 'America/Los_Angeles')::date;
  v_used integer;
begin
  insert into public.ai_usage (day, model, requests) values (v_day, p_model, 0)
  on conflict (day, model) do nothing;

  update public.ai_usage set requests = requests + 1
  where day = v_day and model = p_model and requests < p_budget
  returning requests into v_used;

  return v_used is not null;
end;
$$;

revoke execute on function ai_take(text, integer) from public, anon, authenticated;
