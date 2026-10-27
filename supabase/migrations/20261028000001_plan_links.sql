-- KG Lead (2026-10-28): a procurement plan (P0) joins the project it turned into, so the project and its
-- budget count once and the statuses given while it was a plan follow it.
--
-- e-GP gives no link between plan_no and project_no (different running numbers), so a pair is matched when
-- all of these hold:
--   1. same agency (dept_code)
--   2. the plan budget equals, to the baht, the budget of one of the project's B0 / 15 / D0
--   3. that announcement came out on or after the plan
--   4. the match is unique both ways: one plan <-> one project; anything ambiguous stays apart

create function plan_links()
returns table (plan_no text, project_no text)
language sql
stable
set search_path = ''
as $$
  with p as (
    select distinct a.plan_no::text as plan_no, a.dept_code, d.budget_thb, a.pub_date
    from public.announcements a join public.announcement_details d on d.announcement_id = a.id
    where a.announce_type = 'P0' and d.budget_thb > 0 and a.dept_code is not null
  ),
  j as (
    select distinct a.project_no::text as project_no, a.dept_code, d.budget_thb, a.pub_date
    from public.announcements a join public.announcement_details d on d.announcement_id = a.id
    where a.announce_type in ('B0', '15', 'D0') and d.budget_thb > 0 and a.project_no is not null
  ),
  pairs as (
    select distinct p.plan_no, j.project_no
    from p join j on j.dept_code = p.dept_code and j.budget_thb = p.budget_thb and j.pub_date >= p.pub_date
  )
  select x.plan_no, x.project_no from pairs x
  where (select count(*) from pairs y where y.plan_no = x.plan_no) = 1
    and (select count(*) from pairs y where y.project_no = x.project_no) = 1;
$$;
revoke execute on function plan_links() from public, anon, authenticated;

-- Leads: a matched plan takes its project's key; statuses saved on either key count.
create or replace function web_leads(p_from date, p_to date)
returns setof jsonb
language sql
stable
set search_path = ''
as $$
  with links as (select * from public.plan_links()),
  base as (
    select a.id, a.announce_type, a.project_no, a.plan_no, a.method, a.title, a.link, a.pub_date, a.dept_name,
           c.score, c.category, c.reason, d.budget_thb as own_budget, d.bid_date, d.extracted,
           public.email_date(a.first_seen_at) as email_date,
           case when a.announce_type = 'P0' then coalesce(lp.project_no, 'P:' || a.plan_no) else a.project_no end as lead_key,
           case when a.announce_type = 'P0' then lp.plan_no else lj.plan_no end as linked_plan
    from public.announcements a
    join public.classifications c on c.announcement_id = a.id and c.relevant and c.score >= 50
    left join public.announcement_details d on d.announcement_id = a.id
    left join links lp on a.announce_type = 'P0' and lp.plan_no = a.plan_no
    left join links lj on a.announce_type <> 'P0' and lj.project_no = a.project_no
    where a.announce_type in ('D0', 'B0', '15', 'P0')
      and a.first_seen_at >= (p_from - 10)::timestamp at time zone 'Asia/Bangkok'
      and a.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
  ),
  keyed as (
    select b.*, array_remove(array[b.lead_key, 'P:' || b.linked_plan], null) as keys from base b
  )
  select jsonb_build_object(
    'type', b.announce_type, 'project_no', b.project_no, 'plan_no', b.plan_no, 'lead_key', b.lead_key,
    'linked_plan', b.linked_plan,
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
                   when exists (select 1 from public.lead_events x where x.lead_key = any (b.keys) and x.status = 'bid')
                     then 'lost'
                   else 'other_won' end)
  from keyed b
  left join lateral (
    select ev.status, ev.created_at, u.name from public.lead_events ev
    join public.lead_users u on u.id = ev.user_id
    where ev.lead_key = any (b.keys) order by ev.created_at desc limit 1) e on true
  left join lateral (
    select (select string_agg(x, ', ') from jsonb_array_elements_text(d2.extracted -> 'winners') x) as winners,
           (d2.extracted ->> 'winner_price')::numeric as winner_price
    from public.announcements x join public.announcement_details d2 on d2.announcement_id = x.id
    where x.project_no = b.project_no and x.announce_type = 'W0'
      and jsonb_typeof(d2.extracted -> 'winners') = 'array' and jsonb_array_length(d2.extracted -> 'winners') > 0
    order by x.first_seen_at desc limit 1) w on b.project_no is not null
  where b.email_date between p_from and p_to;
$$;

-- Status tracking: events saved on a matched plan's key move to its project.
create or replace function web_tracking()
returns setof jsonb
language sql
stable
set search_path = ''
as $$
  with links as (select * from public.plan_links()),
  evk as (
    select e.*, coalesce(l.project_no, e.lead_key) as k
    from public.lead_events e left join links l on e.lead_key = 'P:' || l.plan_no
  ),
  ev as (
    select k as lead_key, count(*)::int as n_events from evk group by k
  ),
  last_ev as (
    select distinct on (e.k) e.k as lead_key, e.status, e.created_at, e.bid_price, e.reasons, e.note, u.name
    from evk e join public.lead_users u on u.id = e.user_id
    order by e.k, e.created_at desc
  )
  select jsonb_build_object(
    'lead_key', ev.lead_key, 'n_events', ev.n_events,
    'status', l.status, 'status_at', l.created_at, 'status_by', l.name, 'bid_price', l.bid_price,
    'reasons', l.reasons, 'note', l.note,
    'title', info.title, 'dept_name', info.dept_name, 'type', info.announce_type, 'link', info.link,
    'linked_plan', (select lk.plan_no from links lk where lk.project_no = ev.lead_key),
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
                   when exists (select 1 from evk x where x.k = ev.lead_key and x.status = 'bid')
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

-- One lead: an old plan link opens its project; the plan's announcement and statuses come along.
create or replace function lead_detail(p_key text)
returns jsonb
language sql
stable
set search_path = ''
as $$
  with links as (select * from public.plan_links()),
  k as (select coalesce((select l.project_no from links l where 'P:' || l.plan_no = p_key), p_key) as key),
  plans as (select l.plan_no from links l, k where l.project_no = k.key)
  select jsonb_build_object(
    'lead_key', (select key from k),
    'linked_plan', (select min(plan_no) from plans),
    'announcements', coalesce((
      select jsonb_agg(jsonb_build_object(
               'type', a.announce_type, 'title', a.title, 'link', a.link, 'pub_date', a.pub_date,
               'dept_name', a.dept_name, 'method', a.method, 'project_no', a.project_no, 'plan_no', a.plan_no,
               'budget_thb', d.budget_thb, 'bid_date', d.bid_date, 'bid_time', d.extracted ->> 'bid_time',
               'expected_month', d.extracted ->> 'expected_month', 'province', d.extracted ->> 'province',
               'winners', d.extracted -> 'winners', 'winner_price', d.extracted -> 'winner_price')
             order by a.pub_date, a.id)
      from public.announcements a
      left join public.announcement_details d on d.announcement_id = a.id, k
      where (k.key like 'P:%' and a.announce_type = 'P0' and a.plan_no = substr(k.key, 3))
         or (k.key not like 'P:%' and (a.project_no = k.key
              or (a.announce_type = 'P0' and a.plan_no in (select plan_no from plans))))), '[]'::jsonb),
    'events', coalesce((
      select jsonb_agg(jsonb_build_object(
               'status', e.status, 'reasons', e.reasons, 'bid_price', e.bid_price, 'note', e.note,
               'by', u.name, 'at', e.created_at)
             order by e.created_at)
      from public.lead_events e join public.lead_users u on u.id = e.user_id, k
      where e.lead_key = k.key or e.lead_key in (select 'P:' || plan_no from plans)), '[]'::jsonb));
$$;
