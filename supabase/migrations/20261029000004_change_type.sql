-- ผลที่เปลี่ยนแปลง: change_type = the W1/W2 itself, so the box still says "ยกเลิกผู้ชนะ" after a new
-- winner is announced, while "ตอนนี้" shows that new winner (project_award).
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
  seen as (
    -- the latest W0/W2 of each project seen in the range (W0 rows only for projects in our category)
    select distinct on (a.project_no) a.*
    from public.announcements a
    where a.announce_type in ('W0', 'W2')
      and a.first_seen_at >= (p_from - 10)::timestamp at time zone 'Asia/Bangkok'
      and a.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
      and exists (select 1 from public.announcements y
                  join public.classifications c on c.announcement_id = y.id and c.relevant
                  where y.project_no = a.project_no)
    order by a.project_no, a.first_seen_at desc, a.id desc
  ),
  changed_seen as (
    -- the latest W1/W2 of each project seen in the range (a project may get several, one per lot)
    select distinct on (a.project_no) a.*
    from public.announcements a
    where a.announce_type in ('W1', 'W2')
      and a.first_seen_at >= (p_from - 10)::timestamp at time zone 'Asia/Bangkok'
      and a.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
      and exists (select 1 from public.announcements y
                  join public.classifications c on c.announcement_id = y.id and c.relevant
                  where y.project_no = a.project_no)
    order by a.project_no, a.pub_date desc, a.first_seen_at desc, a.id desc
  ),
  rows as (
    select 'result' as kind, a.project_no, a.title, a.dept_name, a.method,
           coalesce(d.extracted ->> 'province', pi.province) as province, a.pub_date,
           w.winners, w.winner_price, w.ours,
           case when l.first_seen < a.first_seen_at then l.types end as lead_types,
           pi.budget_thb, a.link, a.first_seen_at, w.changed, case when w.changed then w.first_winners end as prev_winners,
           false as withdrawn, null::text as change_type
    from seen a
    left join public.announcement_details d on d.announcement_id = a.id
    cross join lateral public.project_award(a.project_no) w
    left join leads l on l.project_no = a.project_no
    left join project_info pi on pi.project_no = a.project_no
    where w.awarded and w.winners is not null
    union all
    select 'changed', a.project_no, a.title, a.dept_name, a.method, pi.province, a.pub_date,
           w.winners, w.winner_price, w.ours, l.types, pi.budget_thb, a.link, a.first_seen_at, true,
           w.first_winners, w.withdrawn, a.announce_type
    from changed_seen a
    cross join lateral public.project_award(a.project_no) w
    left join leads l on l.project_no = a.project_no
    left join project_info pi on pi.project_no = a.project_no
    union all
    select 'cancelled', a.project_no, a.title, a.dept_name, a.method, pi.province, a.pub_date,
           null, null, false, l.types, pi.budget_thb, a.link, a.first_seen_at, false, null, false, null
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
