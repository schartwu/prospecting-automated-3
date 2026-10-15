-- The e-GP RSS server timed out on every request on a weekday morning (09:44 and 10:21 Bangkok,
-- 2026-10-15), so the department sweep moves to the night and runs itself in chunks.

-- Which deptId codes the sweep has tried, so each night continues where the last one stopped.
create table sweep_attempts (
  code           text primary key,
  last_tried_at  timestamptz not null,
  ok             boolean not null,   -- the feed answered (with or without items)
  found          boolean not null    -- it had announcements; the code was added to departments
);
alter table sweep_attempts enable row level security;

-- Codes to try next: not a known department, and not answered within the last 90 days
-- (failed attempts are retried the next night). Lowest numbers first.
create or replace function next_sweep_codes(p_limit integer)
returns table (code text)
language sql
stable
set search_path = ''
as $$
  select lpad(n::text, 4, '0') as code
  from generate_series(1, 9999) as n
  where not exists (select 1 from public.departments d where d.code = lpad(n::text, 4, '0'))
    and not exists (select 1 from public.sweep_attempts s
                    where s.code = lpad(n::text, 4, '0') and s.ok
                      and s.last_tried_at > now() - interval '90 days')
  order by n
  limit p_limit;
$$;
revoke execute on function next_sweep_codes(integer) from public, anon, authenticated;

-- 21:00 Bangkok every night, after the evening pipeline: sweep the next 2,500 codes.
select cron.schedule('egp-night-sweep', '0 14 * * *', $$select public.trigger_workflow('sweep.yml')$$);
