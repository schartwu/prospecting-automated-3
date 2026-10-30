-- Purchasing units seen in announcement documents. An e-GP page names its file after the unit that published
-- it ("templateName = 'announcewin_020473000005_69109346498.html'", P0 pages 'aplt_<unit>_M...'), so enrich.py
-- notes the unit of every page it already reads (no extra requests). Tested 30 Oct 2026: the RSS answers these
-- codes as deptsubId (020473000005 กองทัพบก นครปฐม, 0700300077 กรมชลประทาน, 5031000000), and agencies without
-- a 4-digit code have a 10-digit deptId (1410400700 มหาวิทยาลัยรามคำแหง: 20 items).
--   - units of a department whose feed hit the 20-item cap, in Sales' provinces -> departments (deptsubId)
--   - codes of announcements whose department is unknown -> candidates that scripts/units.py tries on the RSS
create table if not exists dept_units (
  code        text primary key,
  parent_code text,                 -- department the announcement came from (null: nationwide feed)
  province    text,
  seen        integer not null default 1,
  first_seen  timestamptz not null default now(),
  last_seen   timestamptz not null default now(),
  status      text not null default 'seen'
              check (status in ('seen', 'added', 'not_found')),
  tested_at   timestamptz
);
alter table dept_units enable row level security;

-- rows: [{code, parent_code, province}], one per page read
create or replace function note_units(p_rows jsonb)
returns integer
language sql
set search_path = ''
as $$
  with r as (
    select code, max(parent_code) parent_code, max(province) province, count(*)::integer n
    from jsonb_to_recordset(p_rows) as x(code text, parent_code text, province text)
    where code ~ '^\d{8,20}$'
    group by code
  ), ins as (
    insert into public.dept_units as u (code, parent_code, province, seen)
    select code, parent_code, province, n from r
    on conflict (code) do update
      set seen = u.seen + excluded.seen, last_seen = now(),
          parent_code = coalesce(u.parent_code, excluded.parent_code),
          province = coalesce(u.province, excluded.province)
    returning 1
  )
  select count(*)::integer from ins;
$$;

-- Units of capped departments in Sales' provinces join the evening collection; units added before that have
-- had no announcement for 45 days are switched off again.
create or replace function promote_units(p_provinces text[])
returns jsonb
language plpgsql
set search_path = ''
as $$
declare v_added integer; v_off integer;
begin
  with pick as (
    select u.code, p.name parent_name, u.province
    from public.dept_units u
    join public.departments p on p.code = u.parent_code
    where u.status = 'seen'
      and u.province = any (p_provinces)
      and u.code <> u.parent_code
      and not exists (select 1 from public.departments d where d.code = u.code)
      and exists (select 1 from public.capped_feeds c
                  where c.dept_code = u.parent_code and c.last_capped_at > now() - interval '7 days'
                    and c.announce_type in ('P0', '15', 'B0', 'D0', 'W0'))
  ), ins as (
    insert into public.departments (code, param, name, source, active)
    select code, 'deptsubId', parent_name || ' · หน่วยจัดซื้อ ' || code || ' จ.' || province, 'unit', true
    from pick
    on conflict (code) do nothing
    returning code
  )
  update public.dept_units u set status = 'added' from ins where u.code = ins.code;
  get diagnostics v_added = row_count;

  update public.departments d set active = false
  where d.source = 'unit' and d.active and d.created_at < now() - interval '45 days'
    and not exists (select 1 from public.announcements a
                    where a.dept_code = d.code and a.first_seen_at > now() - interval '45 days');
  get diagnostics v_off = row_count;
  return jsonb_build_object('added', v_added, 'switched_off', v_off);
end; $$;

-- Codes of agencies the collection does not know yet (universities, schools...), in Sales' provinces,
-- not tried in the last 30 days. scripts/units.py tries each on the RSS as deptId, then deptsubId.
create or replace function unit_candidates(p_provinces text[], p_limit integer)
returns table(code text, province text)
language sql
stable
set search_path = ''
as $$
  select u.code, u.province
  from public.dept_units u
  where u.status in ('seen', 'not_found')
    and (u.parent_code is null or not exists (select 1 from public.departments d where d.code = u.parent_code))
    and u.province = any (p_provinces)
    and not exists (select 1 from public.departments d where d.code = u.code)
    and (u.tested_at is null or u.tested_at < now() - interval '30 days')
  order by u.seen desc, u.first_seen
  limit p_limit;
$$;

create or replace function mark_unit(p_code text, p_status text)
returns void
language sql
set search_path = ''
as $$
  update public.dept_units set status = p_status, tested_at = now() where code = p_code;
$$;

revoke execute on function note_units(jsonb) from public, anon, authenticated;
revoke execute on function promote_units(text[]) from public, anon, authenticated;
revoke execute on function unit_candidates(text[], integer) from public, anon, authenticated;
revoke execute on function mark_unit(text, text) from public, anon, authenticated;
