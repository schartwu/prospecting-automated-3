-- Relevant announcements whose linked document has not been read yet, most urgent first.
create or replace function announcements_to_enrich(p_types text[], p_min_score integer, p_limit integer)
returns table (id bigint, announce_type text, link text, pub_date date, title text)
language sql
stable
set search_path = ''
as $$
  select a.id, a.announce_type, a.link, a.pub_date, a.title
  from public.announcements a
  join public.classifications c on c.announcement_id = a.id
  left join public.announcement_details d on d.announcement_id = a.id
  where d.announcement_id is null
    and c.relevant and c.score >= p_min_score
    and a.announce_type = any (p_types)
    and a.first_seen_at > now() - interval '30 days'
  order by array_position(array['D0','B0','15'], a.announce_type), c.score desc
  limit p_limit;
$$;
revoke execute on function announcements_to_enrich(text[], integer, integer) from public, anon, authenticated;

-- Digest rows now carry the bid time window and whether the invitation was changed (D2).
drop function digest_items(timestamptz, text[], integer);
create function digest_items(p_since timestamptz, p_types text[], p_min_score integer default 50)
returns table (
  id bigint, announce_type text, project_no text, plan_no text, method text, title text, link text,
  pub_date date, dept_name text, first_seen_at timestamptz,
  score smallint, category text, reason text,
  budget_thb numeric, bid_date date, bid_time text,
  cancelled boolean, amended boolean, stages text[]
)
language sql
stable
set search_path = ''
as $$
  select a.id, a.announce_type, a.project_no, a.plan_no, a.method, a.title, a.link,
         a.pub_date, a.dept_name, a.first_seen_at,
         c.score, c.category, c.reason,
         -- a 15/B0 of the same project may carry the budget when the D0 document did not
         coalesce(d.budget_thb, (select max(d2.budget_thb) from public.announcements x
                                  join public.announcement_details d2 on d2.announcement_id = x.id
                                  where x.project_no = a.project_no)) as budget_thb,
         d.bid_date, d.extracted ->> 'bid_time' as bid_time,
         exists (select 1 from public.announcements x
                 where x.project_no = a.project_no and x.announce_type = 'D1') as cancelled,
         exists (select 1 from public.announcements x
                 where x.project_no = a.project_no and x.announce_type = 'D2') as amended,
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
