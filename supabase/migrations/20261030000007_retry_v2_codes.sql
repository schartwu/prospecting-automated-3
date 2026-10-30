-- The 198 ten-digit codes from v2 (universities, vocational colleges, education centres...) were tried as
-- deptsubId, never answered and were switched off (20261029000008). On 30 Oct 2026 one of them,
-- 1410400700 มหาวิทยาลัยรามคำแหง, answered as deptId with 20 items, so all of them are tried again by
-- scripts/units.py (deptId, then deptsubId). Sales chose that list for v2, so its codes skip the province filter.
insert into dept_units (code, parent_code, province, seen)
select code, null, null, 0 from departments
where source = 'v2_list' and param = 'deptsubId' and not active
on conflict (code) do nothing;

create or replace function unit_candidates(p_provinces text[], p_limit integer)
returns table(code text, province text)
language sql
stable
set search_path = ''
as $$
  select u.code, u.province
  from public.dept_units u
  left join public.departments v2 on v2.code = u.code and v2.source = 'v2_list'
  where u.status in ('seen', 'not_found')
    and (u.parent_code is null or not exists (select 1 from public.departments d where d.code = u.parent_code))
    and (u.province = any (p_provinces) or v2.code is not null)
    and not exists (select 1 from public.departments d where d.code = u.code and d.active)
    and (u.tested_at is null or u.tested_at < now() - interval '30 days')
  order by (v2.code is not null) desc, u.seen desc, u.first_seen
  limit p_limit;
$$;
revoke execute on function unit_candidates(text[], integer) from public, anon, authenticated;
