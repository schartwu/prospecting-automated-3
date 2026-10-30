-- An item comes back from the nationwide feed (no department) and from its department's feed (same link).
-- Shard 0 loads first, so the nationwide copy was stored and the department copy only bumped last_seen_at:
-- 1,083 rows (D0 208) had no dept_code, which also left their province to the title/document guess.
-- Now a later copy that knows the department fills it in. The feed repeats items for about a week, so recent
-- rows fix themselves on the next evening runs.
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
    on conflict (announce_type, link, item_no) do update
      set last_seen_at = greatest(a.last_seen_at, excluded.last_seen_at),
          dept_code = coalesce(a.dept_code, excluded.dept_code),
          dept_name = case when a.dept_code is null and excluded.dept_code is not null
                           then excluded.dept_name else a.dept_name end
    returning (xmax = 0) as inserted
  )
  select count(*) filter (where inserted)::integer from ins;
$$;

-- Local governments found by scripts/probe_local.py have placeholder names ("หน่วยงานรหัส 6200102 (อบต. ...)")
-- until a document names them. enrich.py reads one document per department each evening (latest HTML page,
-- W0 first: those are short pages) and set_department_name stores the name.
create or replace function departments_to_name(p_limit integer)
returns table(code text, link text)
language sql
stable
set search_path = ''
as $$
  select d.code, x.link
  from public.departments d
  cross join lateral (
    select a.link from public.announcements a
    where a.dept_code = d.code and a.link like '%ShowHTMLFile%'
    order by (a.announce_type = 'W0') desc, a.id desc
    limit 1) x
  where d.active and d.name like 'หน่วยงานรหัส %'
  -- A different order each day, so a department whose page never names it does not block the others.
  order by md5(d.code || current_date::text)
  limit p_limit;
$$;
revoke execute on function departments_to_name(integer) from public, anon, authenticated;
