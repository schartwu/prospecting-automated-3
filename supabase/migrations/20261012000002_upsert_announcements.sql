-- Bulk upsert used by the collector. New items are inserted with their run id; items already seen
-- (the feed repeats them for ~1 week) only get last_seen_at bumped. Returns how many were new.
create or replace function upsert_announcements(p_run_id bigint, p_items jsonb)
returns integer
language sql
set search_path = ''
as $$
  with ins as (
    insert into public.announcements as a
      (announce_type, project_no, plan_no, method, title, link, description, pub_date,
       dept_code, dept_name, first_seen_run, first_seen_at, last_seen_at, raw)
    select i.announce_type, i.project_no, i.plan_no, i.method, i.title, i.link, i.description, i.pub_date,
           i.dept_code, i.dept_name, p_run_id, i.seen_at, i.seen_at, i.raw
    from jsonb_to_recordset(p_items) as i(
      announce_type text, project_no text, plan_no text, method text, title text, link text,
      description text, pub_date date, dept_code text, dept_name text, seen_at timestamptz, raw jsonb)
    on conflict (announce_type, link) do update
      set last_seen_at = greatest(a.last_seen_at, excluded.last_seen_at)
    returning (xmax = 0) as inserted
  )
  select count(*) filter (where inserted)::integer from ins;
$$;

-- Only the collector (service role) may call it.
revoke execute on function upsert_announcements(bigint, jsonb) from public, anon, authenticated;
