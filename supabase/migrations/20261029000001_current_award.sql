-- The result of a project is its latest winner announcement: W0 (winners), W2 (winners changed) or
-- W1 (winners withdrawn). Every list reads it from project_award(), so a W2 naming OfficeMate turns a
-- loss into a win everywhere, and a W1 sends the project back to "waiting for the result".
-- A project counts as awarded as soon as a W0/W2 exists, even when its document could not be read yet
-- (winners null): it is no longer a lead (Lead tab hides it, status updates close).

create or replace function project_award(p_project text)
returns table (
  awarded boolean,          -- latest is W0/W2
  withdrawn boolean,        -- latest is W1
  winners text,             -- of the latest W0/W2 (null: not read yet)
  winner_price numeric,
  ours boolean,
  at timestamptz,           -- when the system first saw the latest announcement
  changed boolean,          -- the project has a W1 or W2
  first_winners text        -- of the first W0 that was read, to show "was X"
)
language sql
stable
set search_path = ''
as $$
  with ev as (
    select a.announce_type as t, a.pub_date, a.first_seen_at, a.id,
           (select string_agg(x, ', ') from jsonb_array_elements_text(
              case when jsonb_typeof(d.extracted -> 'winners') = 'array' then d.extracted -> 'winners' end) x) as winners,
           (d.extracted ->> 'winner_price')::numeric as price
    from public.announcements a
    left join public.announcement_details d on d.announcement_id = a.id
    where a.project_no = p_project and a.announce_type in ('W0', 'W1', 'W2')
  ),
  -- pub_date first: announcements loaded together (the 9 Oct backfill) share a first_seen_at
  last as (select * from ev order by pub_date desc nulls last, first_seen_at desc, id desc limit 1)
  select l.t <> 'W1', l.t = 'W1',
         case when l.t <> 'W1' then nullif(l.winners, '') end,
         case when l.t <> 'W1' then l.price end,
         l.t <> 'W1' and replace(coalesce(l.winners, ''), 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท',
         l.first_seen_at,
         exists (select 1 from ev where t in ('W1', 'W2')),
         (select nullif(winners, '') from ev where t = 'W0' and winners is not null order by pub_date, first_seen_at, id limit 1)
  from last l;
$$;
revoke execute on function project_award(text) from public, anon, authenticated;

-- Leads: the award comes from project_award; awarded/changed tell the web app to hide it and show 🔄.
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
    'awarded', coalesce(w.awarded, false), 'award_changed', coalesce(w.changed, false),
    'prev_winners', case when w.changed then w.first_winners end,
    'winners', w.winners, 'winner_price', w.winner_price,
    'result', case when not coalesce(w.awarded, false) or w.winners is null then null
                   when w.ours then 'win'
                   when exists (select 1 from public.lead_events x where x.lead_key = any (b.keys) and x.status = 'bid')
                     then 'lost'
                   else 'other_won' end)
  from keyed b
  left join lateral (
    select ev.status, ev.created_at, u.name from public.lead_events ev
    join public.lead_users u on u.id = ev.user_id
    where ev.lead_key = any (b.keys) order by ev.created_at desc limit 1) e on true
  left join lateral public.project_award(b.project_no) w on b.project_no is not null
  where b.email_date between p_from and p_to;
$$;

-- Tracking: same award; a withdrawn award (W1) goes back to "bid, waiting for the result".
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
  ),
  ours as (
    -- projects OfficeMate holds now (latest winner announcement names us)
    select p.project_no, w.at
    from (select distinct a.project_no from public.announcements a
          where a.announce_type in ('W0', 'W2') and a.project_no is not null
            and exists (select 1 from public.announcement_details d where d.announcement_id = a.id
                        and replace(d.extracted ->> 'winners', 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท')) p
    cross join lateral public.project_award(p.project_no) w
    where w.ours
  ),
  tracked as (
    select ev.lead_key, ev.n_events, l.status, l.created_at as status_at, l.name as status_by, l.bid_price,
           l.reasons, l.note, false as auto_result
    from ev join last_ev l on l.lead_key = ev.lead_key
    union all
    -- OfficeMate won a project that went out as a lead, and nobody pressed a status on it
    select o.project_no, 0, null, o.at, null, null, null, null, true
    from ours o
    where not exists (select 1 from ev where ev.lead_key = o.project_no)
      and exists (select 1 from public.announcements x
                  join public.classifications c on c.announcement_id = x.id and c.relevant and c.score >= 50
                  where x.project_no = o.project_no and x.announce_type in ('D0', 'B0', '15'))
  )
  select jsonb_build_object(
    'lead_key', t.lead_key, 'n_events', t.n_events, 'auto_result', t.auto_result,
    'status', t.status, 'status_at', t.status_at, 'status_by', t.status_by, 'bid_price', t.bid_price,
    'reasons', t.reasons, 'note', t.note,
    'title', info.title, 'dept_name', info.dept_name, 'type', info.announce_type, 'link', info.link,
    'method', info.method,
    'linked_plan', (select lk.plan_no from links lk where lk.project_no = t.lead_key),
    'budget_thb', (select max(d.budget_thb) from public.announcements a
                     join public.announcement_details d on d.announcement_id = a.id
                    where (a.project_no = t.lead_key) or ('P:' || a.plan_no = t.lead_key)),
    'bid_date', (select max(d.bid_date) from public.announcements a
                   join public.announcement_details d on d.announcement_id = a.id
                  where a.project_no = t.lead_key and a.announce_type = 'D0'),
    'province', (select min(d.extracted ->> 'province') from public.announcements a
                   join public.announcement_details d on d.announcement_id = a.id
                  where (a.project_no = t.lead_key) or ('P:' || a.plan_no = t.lead_key)),
    'cancelled', exists (select 1 from public.announcements a
                         where a.project_no = t.lead_key and a.announce_type = 'D1'),
    'awarded', coalesce(w.awarded, false), 'award_changed', coalesce(w.changed, false),
    'prev_winners', case when w.changed then w.first_winners end,
    'winners', w.winners, 'winner_price', w.winner_price,
    'result', case when not coalesce(w.awarded, false) or w.winners is null then null
                   when w.ours then 'win'
                   when exists (select 1 from evk x where x.k = t.lead_key and x.status = 'bid')
                     then 'lost'
                   else 'other_won' end)
  from tracked t
  left join lateral (
    select a.title, a.dept_name, a.announce_type, a.link, a.method from public.announcements a
    where ((a.project_no = t.lead_key) or ('P:' || a.plan_no = t.lead_key))
      and a.announce_type in ('D0', 'B0', '15', 'P0')
    order by array_position(array['D0','B0','15','P0'], a.announce_type) limit 1) info on true
  left join lateral public.project_award(t.lead_key) w on t.lead_key not like 'P:%';
$$;

-- Results: one row per project whose winner announcement (W0 or W2) was seen in the range, with the
-- project's current winner; projects whose award was withdrawn (W1) drop out of 'result'.
-- kind 'changed': every W1/W2 seen in the range (the "ผลที่เปลี่ยนแปลง" box), with before and now.
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
  rows as (
    select 'result' as kind, a.project_no, a.title, a.dept_name, a.method,
           coalesce(d.extracted ->> 'province', pi.province) as province, a.pub_date,
           w.winners, w.winner_price, w.ours,
           case when l.first_seen < a.first_seen_at then l.types end as lead_types,
           pi.budget_thb, a.link, a.first_seen_at, w.changed, case when w.changed then w.first_winners end as prev_winners,
           false as withdrawn
    from seen a
    left join public.announcement_details d on d.announcement_id = a.id
    cross join lateral public.project_award(a.project_no) w
    left join leads l on l.project_no = a.project_no
    left join project_info pi on pi.project_no = a.project_no
    where w.awarded and w.winners is not null
    union all
    select 'changed', a.project_no, a.title, a.dept_name, a.method, pi.province, a.pub_date,
           w.winners, w.winner_price, w.ours, l.types, pi.budget_thb, a.link, a.first_seen_at, true,
           w.first_winners, w.withdrawn
    from public.announcements a
    cross join lateral public.project_award(a.project_no) w
    left join leads l on l.project_no = a.project_no
    left join project_info pi on pi.project_no = a.project_no
    where a.announce_type in ('W1', 'W2')
      and a.first_seen_at >= (p_from - 10)::timestamp at time zone 'Asia/Bangkok'
      and a.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
      and exists (select 1 from public.announcements y
                  join public.classifications c on c.announcement_id = y.id and c.relevant
                  where y.project_no = a.project_no)
    union all
    select 'cancelled', a.project_no, a.title, a.dept_name, a.method, pi.province, a.pub_date,
           null, null, false, l.types, pi.budget_thb, a.link, a.first_seen_at, false, null, false
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
