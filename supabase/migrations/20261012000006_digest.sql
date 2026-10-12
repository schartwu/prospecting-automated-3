-- One row per digest email sent, so the next digest only shows what arrived since.
create table digests (
  id          bigint generated always as identity primary key,
  kind        text not null default 'daily',
  sent_at     timestamptz not null default now(),
  since       timestamptz not null,
  n_items     integer not null,
  recipients  text
);
alter table digests enable row level security;

-- Relevant announcements first seen after p_since, with everything the email needs.
create or replace function digest_items(p_since timestamptz, p_types text[], p_min_score integer default 50)
returns table (
  id bigint, announce_type text, project_no text, plan_no text, method text, title text, link text,
  pub_date date, dept_name text, first_seen_at timestamptz,
  score smallint, category text, reason text,
  budget_thb numeric, bid_date date,
  cancelled boolean, stages text[]
)
language sql
stable
set search_path = ''
as $$
  select a.id, a.announce_type, a.project_no, a.plan_no, a.method, a.title, a.link,
         a.pub_date, a.dept_name, a.first_seen_at,
         c.score, c.category, c.reason,
         d.budget_thb, d.bid_date,
         exists (select 1 from public.announcements x
                 where x.project_no = a.project_no and x.announce_type = 'D1') as cancelled,
         (select array_agg(distinct x.announce_type) from public.announcements x
           where x.project_no = a.project_no) as stages
  from public.announcements a
  join public.classifications c on c.announcement_id = a.id
  left join public.announcement_details d on d.announcement_id = a.id
  where c.relevant
    and c.score >= p_min_score
    and a.first_seen_at >= p_since
    and a.announce_type = any (p_types)
  order by c.score desc, a.pub_date desc;
$$;

revoke execute on function digest_items(timestamptz, text[], integer) from public, anon, authenticated;
