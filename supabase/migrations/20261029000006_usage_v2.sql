-- การใช้งาน v2: the admin's own visits stay out of the totals (testing would inflate them), and each person
-- also shows how many statuses they pressed in the last 7 days. web_usage() (no argument) is no longer used.
create or replace function web_usage(p_exclude text[])
returns jsonb
language sql
stable
set search_path = ''
as $$
  with today as (select (now() at time zone 'Asia/Bangkok')::date as d),
  skip as (select id from public.lead_users where lower(email) = any (p_exclude)),
  v as (select v.*, (v.at at time zone 'Asia/Bangkok')::date as day from public.lead_visits v
        where v.at > now() - interval '30 days' and v.user_id not in (select id from skip))
  select jsonb_build_object(
    'online', coalesce((
      select jsonb_agg(jsonb_build_object('name', u.name, 'role', u.role, 'devices', p.n, 'view', p.view, 'last_seen', p.last_seen,
                                          'admin', u.id in (select id from skip))
                       order by p.last_seen desc)
      from (select user_id, count(*) as n, max(last_seen) as last_seen,
                   (array_agg(view order by last_seen desc))[1] as view
            from public.lead_presence where last_seen > now() - interval '2 minutes' group by user_id) p
      join public.lead_users u on u.id = p.user_id), '[]'::jsonb),
    'today_people', (select count(distinct user_id) from v, today where v.day = today.d),
    'today_devices', (select count(distinct device) from v, today where v.day = today.d),
    'week_people', (select count(distinct user_id) from v, today where v.day > today.d - 7),
    'week_devices', (select count(distinct device) from v, today where v.day > today.d - 7),
    'days', coalesce((
      select jsonb_agg(jsonb_build_object('day', d.day, 'people', d.people, 'devices', d.devices, 'views', d.views) order by d.day)
      from (select day, count(distinct user_id) as people, count(distinct device) as devices, count(*) as views
            from v, today where v.day > today.d - 14 group by day) d), '[]'::jsonb),
    'pages', coalesce((
      select jsonb_object_agg(view, n) from (select view, count(*) as n from v, today where v.day > today.d - 7 group by view) x),
      '{}'::jsonb),
    'people', coalesce((
      select jsonb_agg(jsonb_build_object('name', u.name, 'role', u.role, 'admin', u.id in (select id from skip),
               'last_visit', (select max(at) from public.lead_visits x where x.user_id = u.id),
               'days_7', (select count(distinct (x.at at time zone 'Asia/Bangkok')::date) from public.lead_visits x, today
                          where x.user_id = u.id and (x.at at time zone 'Asia/Bangkok')::date > today.d - 7),
               'views_7', (select count(*) from public.lead_visits x, today
                           where x.user_id = u.id and (x.at at time zone 'Asia/Bangkok')::date > today.d - 7),
               'devices_7', (select count(distinct device) from public.lead_visits x, today
                             where x.user_id = u.id and (x.at at time zone 'Asia/Bangkok')::date > today.d - 7),
               'updates_7', (select count(*) from public.lead_events e, today
                             where e.user_id = u.id and (e.created_at at time zone 'Asia/Bangkok')::date > today.d - 7))
             order by u.id)
      from public.lead_users u where u.active), '[]'::jsonb));
$$;
revoke execute on function web_usage(text[]) from public, anon, authenticated;
