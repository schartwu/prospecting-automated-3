-- The API hands back at most 1,000 rows per call (PostgREST max rows). The web lists are returned as one
-- JSON array instead, so a long range is never cut: "ทั้งหมด" in ผลลัพธ์ had 1,386 rows and showed 1,000,
-- losing the rows at the end (all of "ผลที่เปลี่ยนแปลง" and "Lead ถูกยกเลิก").
create or replace function web_list(p_kind text, p_from date default null, p_to date default null)
returns jsonb
language plpgsql
stable
set search_path = ''
as $$
begin
  if p_kind = 'leads' then
    return (select coalesce(jsonb_agg(j), '[]'::jsonb) from public.web_leads(p_from, p_to) j);
  elsif p_kind = 'outcomes' then
    return (select coalesce(jsonb_agg(j), '[]'::jsonb) from public.web_outcomes(p_from, p_to) j);
  elsif p_kind = 'items' then
    return (select coalesce(jsonb_agg(j), '[]'::jsonb) from public.web_items(p_from, p_to) j);
  elsif p_kind = 'tracking' then
    return (select coalesce(jsonb_agg(j), '[]'::jsonb) from public.web_tracking() j);
  end if;
  raise exception 'unknown list %', p_kind;
end;
$$;
revoke execute on function web_list(text, date, date) from public, anon, authenticated;
