-- KG Lead (2026-10-28): ติดตามสถานะ also lists leads OfficeMate won that nobody gave a status (e.g. bid before
-- the system existed), dated by the winner announcement and flagged auto_result. Rows are unordered; the
-- page sorts them.
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
  w0 as (
    select distinct on (a.project_no) a.project_no, a.first_seen_at,
           (select string_agg(x, ', ') from jsonb_array_elements_text(d.extracted -> 'winners') x) as winners,
           (d.extracted ->> 'winner_price')::numeric as winner_price
    from public.announcements a join public.announcement_details d on d.announcement_id = a.id
    where a.announce_type = 'W0'
      and jsonb_typeof(d.extracted -> 'winners') = 'array' and jsonb_array_length(d.extracted -> 'winners') > 0
    order by a.project_no, a.first_seen_at desc
  ),
  tracked as (
    select ev.lead_key, ev.n_events, l.status, l.created_at as status_at, l.name as status_by, l.bid_price,
           l.reasons, l.note, false as auto_result
    from ev join last_ev l on l.lead_key = ev.lead_key
    union all
    -- OfficeMate won a project that went out as a lead, and nobody pressed a status on it
    select w.project_no, 0, null, w.first_seen_at, null, null, null, null, true
    from w0 w
    where replace(w.winners, 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท'
      and not exists (select 1 from ev where ev.lead_key = w.project_no)
      and exists (select 1 from public.announcements x
                  join public.classifications c on c.announcement_id = x.id and c.relevant and c.score >= 50
                  where x.project_no = w.project_no and x.announce_type in ('D0', 'B0', '15'))
  )
  select jsonb_build_object(
    'lead_key', t.lead_key, 'n_events', t.n_events, 'auto_result', t.auto_result,
    'status', t.status, 'status_at', t.status_at, 'status_by', t.status_by, 'bid_price', t.bid_price,
    'reasons', t.reasons, 'note', t.note,
    'title', info.title, 'dept_name', info.dept_name, 'type', info.announce_type, 'link', info.link,
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
    'winners', w.winners, 'winner_price', w.winner_price,
    'result', case when w.winners is null then null
                   when replace(w.winners, 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท' then 'win'
                   when exists (select 1 from evk x where x.k = t.lead_key and x.status = 'bid')
                     then 'lost'
                   else 'other_won' end)
  from tracked t
  left join lateral (
    select a.title, a.dept_name, a.announce_type, a.link from public.announcements a
    where ((a.project_no = t.lead_key) or ('P:' || a.plan_no = t.lead_key))
      and a.announce_type in ('D0', 'B0', '15', 'P0')
    order by array_position(array['D0','B0','15','P0'], a.announce_type) limit 1) info on true
  left join w0 w on w.project_no = t.lead_key;
$$;
