-- Phase 1 coverage: re-read busy feeds in the afternoon, and drop what belonged to the cancelled Phase 2.

-- Feeds (department x type) that returned the full 20 items, so items were probably cut off.
create table capped_feeds (
  dept_code       text not null,
  announce_type   text not null,
  last_capped_at  timestamptz not null,
  primary key (dept_code, announce_type)
);
alter table capped_feeds enable row level security;

create or replace function recent_capped_feeds(p_days integer)
returns table (dept_code text, announce_type text, dept_name text)
language sql
stable
set search_path = ''
as $$
  select f.dept_code, f.announce_type, coalesce(d.name, f.dept_code)
  from public.capped_feeds f
  left join public.departments d on d.code = f.dept_code
  where f.last_capped_at > now() - make_interval(days => p_days)
  order by f.dept_code, f.announce_type;
$$;
revoke execute on function recent_capped_feeds(integer) from public, anon, authenticated;

-- 14:00 and 16:30 Bangkok, Mon-Fri: re-read capped feeds (after the 12:00-13:00 break of the e-GP server).
select cron.schedule('egp-midday-recheck', '0 7 * * 1-5', $$select public.trigger_workflow('recheck.yml')$$);
select cron.schedule('egp-afternoon-recheck', '30 9 * * 1-5', $$select public.trigger_workflow('recheck.yml')$$);

-- Phase 2 (dashboard and Sales feedback) was cancelled on 2026-10-15; the table never held data.
drop table feedback;
