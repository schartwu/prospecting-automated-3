-- KG Lead Loop, step B (2026-10-26): who may open the lead web app, and what they did with each lead.
--
-- A lead is a project (11-digit project_no shared by its B0 / 15 / D0 / W0 / D1) or, for a plan, 'P:' + plan_no.
-- People open the web app with a personal link (lead_users.token). The Edge Function `lead` looks the token
-- up with the service role; nobody else can read these tables (RLS on, no policies).

create table lead_users (
  id bigint generated always as identity primary key,
  name text not null,
  email text not null unique,
  role text not null check (role in ('dv', 'viewer')),   -- dv = Division Manager, the one who updates leads
  token text not null unique default replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
  active boolean not null default true,
  created_at timestamptz not null default now()
);
alter table lead_users enable row level security;

create table lead_events (
  id bigint generated always as identity primary key,
  lead_key text not null,
  status text not null check (status in
    ('received', 'contacted', 'sent_to_mer', 'mer_replied', 'bid', 'no_bid', 'other')),
  reasons text[] not null default '{}',
  bid_price numeric,
  note text,
  user_id bigint not null references lead_users (id),
  created_at timestamptz not null default now(),
  constraint no_bid_needs_reason check (status <> 'no_bid' or cardinality(reasons) > 0),
  constraint other_needs_note check (status <> 'other' or coalesce(btrim(note), '') <> '')
);
alter table lead_events enable row level security;
create index lead_events_key on lead_events (lead_key, created_at desc);

-- Every lead that went out in the morning email in the last p_days days (relevant, score >= 50, Sales'
-- provinces or no province), with its latest status and what e-GP says happened to it.
create function lead_board(p_days integer, p_provinces text[])
returns table (
  lead_key text, title text, dept_name text, province text, types text[], link text,
  budget_thb numeric, bid_date date, score smallint, first_seen_at timestamptz,
  status text, status_at timestamptz, status_by text, n_events integer,
  outcome text, winners text, winner_price numeric
)
language sql
stable
set search_path = ''
as $$
  with lead_ann as (
    select case when a.announce_type = 'P0' then 'P:' || a.plan_no else a.project_no end as lead_key,
           a.*, c.score, d.budget_thb as doc_budget, d.bid_date as doc_bid_date, d.extracted
    from public.announcements a
    join public.classifications c on c.announcement_id = a.id and c.relevant and c.score >= 50
    left join public.announcement_details d on d.announcement_id = a.id
    where a.announce_type in ('D0', 'B0', '15', 'P0')
      and a.first_seen_at > now() - make_interval(days => p_days)
      and coalesce(a.project_no, a.plan_no) is not null
  ),
  leads as (
    select l.lead_key,
           -- the most useful announcement to show: invitation, then draft TOR, reference price, plan
           (array_agg(l.title order by array_position(array['D0','B0','15','P0'], l.announce_type)))[1] as title,
           (array_agg(l.link order by array_position(array['D0','B0','15','P0'], l.announce_type)))[1] as link,
           (array_agg(l.dept_name order by array_position(array['D0','B0','15','P0'], l.announce_type)))[1] as dept_name,
           min(l.extracted ->> 'province') as province,
           array_agg(distinct l.announce_type) as types,
           max(l.doc_budget) as budget_thb, max(l.doc_bid_date) as bid_date,
           max(l.score)::smallint as score, min(l.first_seen_at) as first_seen_at
    from lead_ann l
    group by l.lead_key
  ),
  last_event as (
    select distinct on (e.lead_key) e.lead_key, e.status, e.created_at, u.name
    from public.lead_events e join public.lead_users u on u.id = e.user_id
    order by e.lead_key, e.created_at desc
  ),
  results as (
    select distinct on (a.project_no) a.project_no,
           replace(d.extracted ->> 'winners', 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท' as ours,
           (select string_agg(w, ', ') from jsonb_array_elements_text(d.extracted -> 'winners') w) as winners,
           (d.extracted ->> 'winner_price')::numeric as winner_price
    from public.announcements a
    join public.announcement_details d on d.announcement_id = a.id
    where a.announce_type = 'W0' and jsonb_typeof(d.extracted -> 'winners') = 'array'
      and jsonb_array_length(d.extracted -> 'winners') > 0
    order by a.project_no, a.first_seen_at desc
  )
  select l.lead_key, l.title, l.dept_name, l.province, l.types, l.link, l.budget_thb, l.bid_date, l.score,
         l.first_seen_at, e.status, e.created_at, e.name,
         (select count(*)::integer from public.lead_events x where x.lead_key = l.lead_key),
         case
           when r.ours then 'win'
           when r.project_no is not null and exists (select 1 from public.lead_events x
                                                     where x.lead_key = l.lead_key and x.status = 'bid') then 'lost'
           when r.project_no is not null and e.status is null then 'missed'
           when r.project_no is not null then 'other_won'
           when exists (select 1 from public.announcements x
                        where x.project_no = l.lead_key and x.announce_type = 'D1') then 'cancelled'
         end,
         r.winners, r.winner_price
  from leads l
  left join last_event e on e.lead_key = l.lead_key
  left join results r on r.project_no = l.lead_key
  where l.province is null or l.province = any (p_provinces)
  order by l.first_seen_at desc;
$$;
revoke execute on function lead_board(integer, text[]) from public, anon, authenticated;

-- One lead: its announcements (with documents, budget, bid date) and its history.
create function lead_detail(p_key text)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select jsonb_build_object(
    'lead_key', p_key,
    'announcements', coalesce((
      select jsonb_agg(jsonb_build_object(
               'type', a.announce_type, 'title', a.title, 'link', a.link, 'pub_date', a.pub_date,
               'dept_name', a.dept_name, 'method', a.method, 'project_no', a.project_no, 'plan_no', a.plan_no,
               'budget_thb', d.budget_thb, 'bid_date', d.bid_date, 'bid_time', d.extracted ->> 'bid_time',
               'expected_month', d.extracted ->> 'expected_month', 'province', d.extracted ->> 'province',
               'winners', d.extracted -> 'winners', 'winner_price', d.extracted -> 'winner_price')
             order by a.pub_date, a.id)
      from public.announcements a
      left join public.announcement_details d on d.announcement_id = a.id
      where (p_key like 'P:%' and a.announce_type = 'P0' and a.plan_no = substr(p_key, 3))
         or (p_key not like 'P:%' and a.project_no = p_key)), '[]'::jsonb),
    'events', coalesce((
      select jsonb_agg(jsonb_build_object(
               'status', e.status, 'reasons', e.reasons, 'bid_price', e.bid_price, 'note', e.note,
               'by', u.name, 'at', e.created_at)
             order by e.created_at)
      from public.lead_events e join public.lead_users u on u.id = e.user_id
      where e.lead_key = p_key), '[]'::jsonb));
$$;
revoke execute on function lead_detail(text) from public, anon, authenticated;
