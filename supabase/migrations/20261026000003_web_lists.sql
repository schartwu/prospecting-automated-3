-- KG Lead web app (2026-10-26): the Excel tabs move to the web, with a calendar.
-- A row belongs to the day of the morning email that carried it (or would have: an announcement first
-- seen before the first email, or after the last one, counts for the next morning).

create function email_date(p_seen timestamptz)
returns date
language sql
stable
set search_path = ''
as $$
  select coalesce(
    (select (min(g.sent_at) at time zone 'Asia/Bangkok')::date from public.digests g
      where g.kind = 'daily' and g.sent_at >= p_seen),
    (p_seen at time zone 'Asia/Bangkok')::date + 1);
$$;
revoke execute on function email_date(timestamptz) from public, anon, authenticated;

-- outcome_items now also returns when the result was first seen, so the web app can file it by day.
drop function outcome_items(timestamptz);
create function outcome_items(p_since timestamptz)
returns table (
  kind text, project_no text, title text, dept_name text, province text, pub_date date,
  winners text, winner_price numeric, ours boolean, lead_types text[], budget_thb numeric, link text,
  first_seen_at timestamptz
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
         pi.budget_thb, a.link, a.first_seen_at
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
         null, null, false, l.types, pi.budget_thb, a.link, a.first_seen_at
  from public.announcements a
  join leads l on l.project_no = a.project_no
  left join project_info pi on pi.project_no = a.project_no
  where a.announce_type = 'D1'
    and a.first_seen_at >= p_since;
$$;
revoke execute on function outcome_items(timestamptz) from public, anon, authenticated;

-- Results (W0 / D1) filed under the morning email that carried them.
create function web_outcomes(p_from date, p_to date)
returns setof jsonb
language sql
stable
set search_path = ''
as $$
  select to_jsonb(o) || jsonb_build_object('email_date', public.email_date(o.first_seen_at))
  from public.outcome_items((p_from - 10)::timestamp at time zone 'Asia/Bangkok') o
  where o.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
    and public.email_date(o.first_seen_at) between p_from and p_to;
$$;
revoke execute on function web_outcomes(date, date) from public, anon, authenticated;

-- Every relevant announcement (score >= 50) of the morning emails between p_from and p_to: the rows of the
-- former Excel "รายการ" tab, plus the lead's latest status and what e-GP says happened to the project.
create function web_items(p_from date, p_to date)
returns setof jsonb
language sql
stable
set search_path = ''
as $$
  with base as (
    select a.id, a.announce_type, a.project_no, a.plan_no, a.method, a.title, a.link, a.pub_date, a.dept_name,
           a.first_seen_at, c.score, c.category, c.reason, d.budget_thb as own_budget, d.bid_date, d.extracted,
           public.email_date(a.first_seen_at) as email_date,
           case when a.announce_type = 'P0' then 'P:' || a.plan_no else a.project_no end as lead_key
    from public.announcements a
    join public.classifications c on c.announcement_id = a.id and c.relevant and c.score >= 50
    left join public.announcement_details d on d.announcement_id = a.id
    where a.announce_type in ('D0', 'B0', '15', 'P0', 'W0')
      and a.first_seen_at >= (p_from - 10)::timestamp at time zone 'Asia/Bangkok'
      and a.first_seen_at < (p_to + 1)::timestamp at time zone 'Asia/Bangkok'
  )
  select jsonb_build_object(
    'id', b.id, 'type', b.announce_type, 'project_no', b.project_no, 'plan_no', b.plan_no,
    'lead_key', case when b.announce_type = 'W0' then null else b.lead_key end,
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
    'winners', (select string_agg(w, ', ') from jsonb_array_elements_text(
       case when jsonb_typeof(b.extracted -> 'winners') = 'array' then b.extracted -> 'winners'
            else '[]'::jsonb end) w),
    'winner_price', (b.extracted ->> 'winner_price')::numeric,
    'cancelled', exists (select 1 from public.announcements x
                         where x.project_no = b.project_no and x.announce_type = 'D1'),
    'amended', exists (select 1 from public.announcements x
                       where x.project_no = b.project_no and x.announce_type = 'D2'),
    'status', e.status, 'status_at', e.created_at, 'status_by', e.name,
    'result', case when b.announce_type <> 'W0' then (
       select case when replace(d2.extracted ->> 'winners', 'ํา', 'ำ') ~ 'ออฟฟิศ\s*เมท' then 'win'
                   when exists (select 1 from public.lead_events x
                                where x.lead_key = b.lead_key and x.status = 'bid') then 'lost'
                   else 'other_won' end
       from public.announcements x join public.announcement_details d2 on d2.announcement_id = x.id
       where x.project_no = b.project_no and x.announce_type = 'W0'
         and jsonb_typeof(d2.extracted -> 'winners') = 'array'
         and jsonb_array_length(d2.extracted -> 'winners') > 0
       order by x.first_seen_at desc limit 1) end)
  from base b
  left join lateral (
    select ev.status, ev.created_at, u.name from public.lead_events ev
    join public.lead_users u on u.id = ev.user_id
    where ev.lead_key = b.lead_key order by ev.created_at desc limit 1) e on b.announce_type <> 'W0'
  where b.email_date between p_from and p_to
  order by b.email_date desc, b.score desc;
$$;
revoke execute on function web_items(date, date) from public, anon, authenticated;

-- Days that had a morning email, for the calendar's previous/next buttons.
create function web_email_days()
returns setof date
language sql
stable
set search_path = ''
as $$
  select distinct (sent_at at time zone 'Asia/Bangkok')::date from public.digests where kind = 'daily' order by 1;
$$;
revoke execute on function web_email_days() from public, anon, authenticated;
