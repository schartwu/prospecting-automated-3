-- Classify what Sales acts on first (D0, B0, 15), then plans, then winners, so a run cut short by
-- the Gemini quota still covers the urgent sections of the digest.
create or replace function unclassified_titles(p_types text[], p_limit integer default 200)
returns table (title text, announce_types text[], methods text[], n integer)
language sql
stable
set search_path = ''
as $$
  select a.title,
         array_agg(distinct a.announce_type) as announce_types,
         array_agg(distinct a.method) filter (where a.method is not null) as methods,
         count(*)::integer as n
  from public.announcements a
  left join public.classifications c on c.announcement_id = a.id
  where c.announcement_id is null
    and a.announce_type = any (p_types)
  group by a.title
  order by min(array_position(array['D0','B0','15','P0','W0'], a.announce_type)), max(a.first_seen_at) desc
  limit p_limit;
$$;
