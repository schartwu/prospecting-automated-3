-- Distinct titles that still have unclassified announcements. The same project title shows up as
-- 15, B0, D0, W0..., so the classifier judges each title once and the result is applied to all of them.
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
  order by max(a.first_seen_at) desc
  limit p_limit;
$$;

-- Store one verdict for every unclassified announcement with these titles.
create or replace function save_title_classifications(p_types text[], p_rows jsonb)
returns integer
language sql
set search_path = ''
as $$
  with r as (
    select * from jsonb_to_recordset(p_rows)
      as x(title text, relevant boolean, score smallint, category text, reason text, model text)
  ), ins as (
    insert into public.classifications (announcement_id, relevant, score, category, reason, model)
    select a.id, r.relevant, r.score, r.category, r.reason, r.model
    from r
    join public.announcements a on a.title = r.title and a.announce_type = any (p_types)
    on conflict (announcement_id) do update
      set relevant = excluded.relevant, score = excluded.score, category = excluded.category,
          reason = excluded.reason, model = excluded.model, classified_at = now()
    returning 1
  )
  select count(*)::integer from ins;
$$;

revoke execute on function unclassified_titles(text[], integer) from public, anon, authenticated;
revoke execute on function save_title_classifications(text[], jsonb) from public, anon, authenticated;

-- Long Thai titles can exceed the btree row-size limit (~2.7 kB), so use a hash index for equality.
create index announcements_title_hash_idx on announcements using hash (title);
