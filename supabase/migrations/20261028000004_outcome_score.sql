-- web_outcomes rows carry the project's score (the highest of its relevant announcements, the result itself
-- included), so ผลลัพธ์ and ภาพรวม can filter results by the same score bands as the leads.
create or replace function web_outcomes(p_from date, p_to date)
returns setof jsonb
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
  ),
  rows as (
    select 'result' as kind, a.project_no, a.title, a.dept_name,
           coalesce(d.extracted ->> 'province', pi.province) as province, a.pub_date,
           (select string_agg(w, ', ') from jsonb_array_elements_text(d.extracted -> 'winners') w) as winners,
           (d.extracted ->> 'winner_price')::numeric as winner_price,
           replace(d.extracted ->> 'winners', 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท' as ours,
           case when l.first_seen < a.first_seen_at then l.types end as lead_types,
           pi.budget_thb, a.link, a.first_seen_at
    from public.announcements a
    join public.announcement_details d on d.announcement_id = a.id
    left join leads l on l.project_no = a.project_no
    left join project_info pi on pi.project_no = a.project_no
    where a.announce_type = 'W0'
      and jsonb_typeof(d.extracted -> 'winners') = 'array'
      and jsonb_array_length(d.extracted -> 'winners') > 0
      and a.first_seen_at >= (p_from - 10)::timestamp at time zone 'Asia/Bangkok'
      and a.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
    union all
    select 'cancelled', a.project_no, a.title, a.dept_name, pi.province, a.pub_date,
           null, null, false, l.types, pi.budget_thb, a.link, a.first_seen_at
    from public.announcements a
    join leads l on l.project_no = a.project_no
    left join project_info pi on pi.project_no = a.project_no
    where a.announce_type = 'D1'
      and a.first_seen_at >= (p_from - 10)::timestamp at time zone 'Asia/Bangkok'
      and a.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
  )
  select to_jsonb(r) || jsonb_build_object('email_date', public.email_date(r.first_seen_at),
    'score', (select max(c.score) from public.announcements a
               join public.classifications c on c.announcement_id = a.id and c.relevant
              where a.project_no = r.project_no))
  from rows r
  where public.email_date(r.first_seen_at) between p_from and p_to;
$$;
revoke execute on function web_outcomes(date, date) from public, anon, authenticated;
