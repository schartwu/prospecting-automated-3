-- The API hands back at most 1,000 rows per call, so classify.py only ever saw 1,000 titles a run. With the
-- local governments added (29 Oct 2026) a run brings ~7,000 announcements and 6,176 were left waiting.
-- Same list as unclassified_titles(), as one JSON array.
create or replace function unclassified_titles_json(p_types text[], p_limit integer)
returns jsonb
language sql
stable
set search_path = ''
as $$
  select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb)
  from public.unclassified_titles(p_types, p_limit) t;
$$;
revoke execute on function unclassified_titles_json(text[], integer) from public, anon, authenticated;
