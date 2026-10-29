-- Who uses KG Lead (approved 29 Oct 2026). The Edge Function records, for the person behind each link:
--   lead_visits   one row per page opened (Lead, ติดตามสถานะ, ...), kept 180 days
--   lead_presence the last sign of life of each open browser (a ping every minute while the page is visible)
-- device = a random id the browser keeps for itself, so the shared Monitor link still counts devices.
-- No IP address is stored. Only the admin account (ADMIN_EMAILS of the Edge Function) can read the summary.

create table lead_visits (
  id         bigint generated always as identity primary key,
  user_id    bigint not null references lead_users (id) on delete cascade,
  device     text not null check (device ~ '^[0-9a-f]{16}$'),
  view       text not null,
  at         timestamptz not null default now()
);
create index lead_visits_at on lead_visits (at);
alter table lead_visits enable row level security;

create table lead_presence (
  user_id    bigint not null references lead_users (id) on delete cascade,
  device     text not null check (device ~ '^[0-9a-f]{16}$'),
  view       text not null,
  last_seen  timestamptz not null default now(),
  primary key (user_id, device)
);
alter table lead_presence enable row level security;

-- Summary for the "การใช้งาน" page: online now (seen in the last 2 minutes), today and 7 days, and per person.
create or replace function web_usage()
returns jsonb
language sql
stable
set search_path = ''
as $$
  with today as (select (now() at time zone 'Asia/Bangkok')::date as d),
  v as (select v.*, (v.at at time zone 'Asia/Bangkok')::date as day from public.lead_visits v
        where v.at > now() - interval '30 days')
  select jsonb_build_object(
    'online', coalesce((
      select jsonb_agg(jsonb_build_object('name', u.name, 'role', u.role, 'devices', p.n, 'view', p.view, 'last_seen', p.last_seen)
                       order by p.last_seen desc)
      from (select user_id, count(*) as n, max(last_seen) as last_seen,
                   (array_agg(view order by last_seen desc))[1] as view
            from public.lead_presence where last_seen > now() - interval '2 minutes' group by user_id) p
      join public.lead_users u on u.id = p.user_id), '[]'::jsonb),
    'online_devices', (select count(*) from public.lead_presence where last_seen > now() - interval '2 minutes'),
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
      select jsonb_agg(jsonb_build_object('name', u.name, 'role', u.role,
               'last_visit', (select max(at) from public.lead_visits x where x.user_id = u.id),
               'days_7', (select count(distinct day) from v, today where v.user_id = u.id and v.day > today.d - 7),
               'views_7', (select count(*) from v, today where v.user_id = u.id and v.day > today.d - 7),
               'devices_7', (select count(distinct device) from v, today where v.user_id = u.id and v.day > today.d - 7))
             order by u.id)
      from public.lead_users u where u.active), '[]'::jsonb));
$$;
revoke execute on function web_usage() from public, anon, authenticated;

-- Weekly cleanup also trims visits older than 180 days and browsers gone for 30 days.
create or replace function cleanup_old_data()
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_deleted integer;
  v_raw_cleared integer;
  v_ai integer;
  v_visits integer;
begin
  delete from public.announcements a
  where a.first_seen_at < now() - interval '60 days'
    and not exists (select 1 from public.classifications c where c.announcement_id = a.id and c.relevant);
  get diagnostics v_deleted = row_count;

  update public.announcements set raw = '{}'::jsonb
  where first_seen_at < now() - interval '14 days' and raw <> '{}'::jsonb;
  get diagnostics v_raw_cleared = row_count;

  delete from public.ai_usage where day < current_date - 30;
  get diagnostics v_ai = row_count;

  delete from public.lead_visits where at < now() - interval '180 days';
  get diagnostics v_visits = row_count;
  delete from public.lead_presence where last_seen < now() - interval '30 days';

  return jsonb_build_object('announcements_deleted', v_deleted, 'raw_cleared', v_raw_cleared,
                            'ai_usage_deleted', v_ai, 'visits_deleted', v_visits,
                            'db_size', pg_size_pretty(pg_database_size(current_database())));
end;
$$;
revoke execute on function cleanup_old_data() from public, anon, authenticated;
