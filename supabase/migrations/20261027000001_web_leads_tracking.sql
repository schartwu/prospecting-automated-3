-- KG Lead web redesign (2026-10-27): leads and results are separate pages, plus a status-tracking page.

-- Leads only (D0 / B0 / 15 / P0) of the morning emails between p_from and p_to; W0 rows live in web_outcomes.
create function web_leads(p_from date, p_to date)
returns setof jsonb
language sql
stable
set search_path = ''
as $$
  with base as (
    select a.id, a.announce_type, a.project_no, a.plan_no, a.method, a.title, a.link, a.pub_date, a.dept_name,
           c.score, c.category, c.reason, d.budget_thb as own_budget, d.bid_date, d.extracted,
           public.email_date(a.first_seen_at) as email_date,
           case when a.announce_type = 'P0' then 'P:' || a.plan_no else a.project_no end as lead_key
    from public.announcements a
    join public.classifications c on c.announcement_id = a.id and c.relevant and c.score >= 50
    left join public.announcement_details d on d.announcement_id = a.id
    where a.announce_type in ('D0', 'B0', '15', 'P0')
      and a.first_seen_at >= (p_from - 10)::timestamp at time zone 'Asia/Bangkok'
      and a.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
  )
  select jsonb_build_object(
    'type', b.announce_type, 'project_no', b.project_no, 'plan_no', b.plan_no, 'lead_key', b.lead_key,
    'method', b.method, 'title', b.title, 'link', b.link, 'pub_date', b.pub_date, 'dept_name', b.dept_name,
    'email_date', b.email_date, 'score', b.score, 'category', b.category, 'reason', b.reason,
    'budget_thb', coalesce(
       (select max(d2.budget_thb) from public.announcements x
          join public.announcement_details d2 on d2.announcement_id = x.id
         where x.project_no = b.project_no and x.announce_type in ('D0', 'B0')
           and d2.extracted ->> 'source' = 'regex'),
       b.own_budget,
       (select max(d2.budget_thb) from public.announcements x
          join public.announcement_details d2 on d2.announcement_id = x.id
         where x.project_no = b.project_no)),
    'bid_date', b.bid_date, 'bid_time', b.extracted ->> 'bid_time',
    'expected_month', b.extracted ->> 'expected_month',
    'province', coalesce(b.extracted ->> 'province',
       (select min(d2.extracted ->> 'province') from public.announcements x
          join public.announcement_details d2 on d2.announcement_id = x.id
         where x.project_no = b.project_no)),
    'cancelled', exists (select 1 from public.announcements x
                         where x.project_no = b.project_no and x.announce_type = 'D1'),
    'amended', exists (select 1 from public.announcements x
                       where x.project_no = b.project_no and x.announce_type = 'D2'),
    'status', e.status, 'status_at', e.created_at, 'status_by', e.name,
    'winners', w.winners, 'winner_price', w.winner_price,
    'result', case when w.winners is null then null
                   when replace(w.winners, 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท' then 'win'
                   when exists (select 1 from public.lead_events x where x.lead_key = b.lead_key and x.status = 'bid')
                     then 'lost'
                   else 'other_won' end)
  from base b
  left join lateral (
    select ev.status, ev.created_at, u.name from public.lead_events ev
    join public.lead_users u on u.id = ev.user_id
    where ev.lead_key = b.lead_key order by ev.created_at desc limit 1) e on true
  left join lateral (
    select (select string_agg(x, ', ') from jsonb_array_elements_text(d2.extracted -> 'winners') x) as winners,
           (d2.extracted ->> 'winner_price')::numeric as winner_price
    from public.announcements x join public.announcement_details d2 on d2.announcement_id = x.id
    where x.project_no = b.project_no and x.announce_type = 'W0'
      and jsonb_typeof(d2.extracted -> 'winners') = 'array' and jsonb_array_length(d2.extracted -> 'winners') > 0
    order by x.first_seen_at desc limit 1) w on b.project_no is not null
  where b.email_date between p_from and p_to;
$$;
revoke execute on function web_leads(date, date) from public, anon, authenticated;

-- Every lead someone has given a status, whatever day it came in: the "ติดตามสถานะ" page.
create function web_tracking()
returns setof jsonb
language sql
stable
set search_path = ''
as $$
  with ev as (
    select lead_key, count(*)::int as n_events from public.lead_events group by lead_key
  ),
  last_ev as (
    select distinct on (e.lead_key) e.lead_key, e.status, e.created_at, e.bid_price, e.reasons, e.note, u.name
    from public.lead_events e join public.lead_users u on u.id = e.user_id
    order by e.lead_key, e.created_at desc
  )
  select jsonb_build_object(
    'lead_key', ev.lead_key, 'n_events', ev.n_events,
    'status', l.status, 'status_at', l.created_at, 'status_by', l.name, 'bid_price', l.bid_price,
    'reasons', l.reasons, 'note', l.note,
    'title', info.title, 'dept_name', info.dept_name, 'type', info.announce_type, 'link', info.link,
    'budget_thb', (select max(d.budget_thb) from public.announcements a
                     join public.announcement_details d on d.announcement_id = a.id
                    where (a.project_no = ev.lead_key) or ('P:' || a.plan_no = ev.lead_key)),
    'bid_date', (select max(d.bid_date) from public.announcements a
                   join public.announcement_details d on d.announcement_id = a.id
                  where a.project_no = ev.lead_key and a.announce_type = 'D0'),
    'province', (select min(d.extracted ->> 'province') from public.announcements a
                   join public.announcement_details d on d.announcement_id = a.id
                  where (a.project_no = ev.lead_key) or ('P:' || a.plan_no = ev.lead_key)),
    'cancelled', exists (select 1 from public.announcements a
                         where a.project_no = ev.lead_key and a.announce_type = 'D1'),
    'winners', w.winners, 'winner_price', w.winner_price,
    'result', case when w.winners is null then null
                   when replace(w.winners, 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท' then 'win'
                   when exists (select 1 from public.lead_events x where x.lead_key = ev.lead_key and x.status = 'bid')
                     then 'lost'
                   else 'other_won' end)
  from ev
  join last_ev l on l.lead_key = ev.lead_key
  left join lateral (
    select a.title, a.dept_name, a.announce_type, a.link from public.announcements a
    where ((a.project_no = ev.lead_key) or ('P:' || a.plan_no = ev.lead_key))
      and a.announce_type in ('D0', 'B0', '15', 'P0')
    order by array_position(array['D0','B0','15','P0'], a.announce_type) limit 1) info on true
  left join lateral (
    select (select string_agg(x, ', ') from jsonb_array_elements_text(d.extracted -> 'winners') x) as winners,
           (d.extracted ->> 'winner_price')::numeric as winner_price
    from public.announcements a join public.announcement_details d on d.announcement_id = a.id
    where a.project_no = ev.lead_key and a.announce_type = 'W0'
      and jsonb_typeof(d.extracted -> 'winners') = 'array' and jsonb_array_length(d.extracted -> 'winners') > 0
    order by a.first_seen_at desc limit 1) w on true
  order by l.created_at desc;
$$;
revoke execute on function web_tracking() from public, anon, authenticated;
