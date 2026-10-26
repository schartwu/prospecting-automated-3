-- KG Lead Loop, step A (2026-10-26): outcomes the system can tell on its own, for the Monday report.
--   result    : a W0 whose winner was read; ours = OfficeMate won; lead_types = the earlier announcements
--               of the same project that went out as leads (B0 / 15 / D0, relevant, score >= 50)
--   cancelled : a D1 (invitation cancelled) for a project that went out as a lead
-- OfficeMate bids as one company: "บริษัท ออฟฟิศเมท (ไทย) จำกัด". Some documents spell ำ as ํ + า.
create function outcome_items(p_since timestamptz)
returns table (
  kind text, project_no text, title text, dept_name text, province text, pub_date date,
  winners text, winner_price numeric, ours boolean, lead_types text[], budget_thb numeric, link text
)
language sql
stable
set search_path = ''
as $$
  with leads as (
    select x.project_no, array_agg(distinct x.announce_type order by x.announce_type) as types,
           min(x.first_seen_at) as first_seen
    from public.announcements x
    join public.classifications c on c.announcement_id = x.id and c.relevant and c.score >= 50
    where x.announce_type in ('B0', '15', 'D0') and x.project_no is not null
    group by x.project_no
  ),
  project_info as (
    select x.project_no, min(d.extracted ->> 'province') as province, max(d.budget_thb) as budget_thb
    from public.announcements x
    join public.announcement_details d on d.announcement_id = x.id
    where x.project_no is not null
    group by x.project_no
  )
  select 'result', a.project_no, a.title, a.dept_name,
         coalesce(d.extracted ->> 'province', pi.province), a.pub_date,
         (select string_agg(w, ', ') from jsonb_array_elements_text(d.extracted -> 'winners') w),
         (d.extracted ->> 'winner_price')::numeric,
         replace(d.extracted ->> 'winners', 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท',
         case when l.first_seen < a.first_seen_at then l.types end,
         pi.budget_thb, a.link
  from public.announcements a
  join public.announcement_details d on d.announcement_id = a.id
  left join leads l on l.project_no = a.project_no
  left join project_info pi on pi.project_no = a.project_no
  where a.announce_type = 'W0'
    and a.first_seen_at >= p_since
    and jsonb_typeof(d.extracted -> 'winners') = 'array'
    and jsonb_array_length(d.extracted -> 'winners') > 0
  union all
  select 'cancelled', a.project_no, a.title, a.dept_name, pi.province, a.pub_date,
         null, null, false, l.types, pi.budget_thb, a.link
  from public.announcements a
  join leads l on l.project_no = a.project_no
  left join project_info pi on pi.project_no = a.project_no
  where a.announce_type = 'D1'
    and a.first_seen_at >= p_since;
$$;
revoke execute on function outcome_items(timestamptz) from public, anon, authenticated;
