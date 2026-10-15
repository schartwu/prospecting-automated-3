-- enrich.py also needs the department, to replace placeholder names of swept departments with the
-- name printed at the top of the announcement ("ประกาศ<หน่วยงาน> เรื่อง ...").
drop function announcements_to_enrich(text[], integer, integer);
create function announcements_to_enrich(p_types text[], p_min_score integer, p_limit integer)
returns table (id bigint, announce_type text, link text, pub_date date, title text, dept_code text,
               dept_needs_name boolean)
language sql
stable
set search_path = ''
as $$
  select a.id, a.announce_type, a.link, a.pub_date, a.title, a.dept_code,
         coalesce(dep.name like 'หน่วยงานรหัส %', false)
  from public.announcements a
  join public.classifications c on c.announcement_id = a.id
  left join public.announcement_details d on d.announcement_id = a.id
  left join public.departments dep on dep.code = a.dept_code
  where d.announcement_id is null
    and c.relevant and c.score >= p_min_score
    and a.announce_type = any (p_types)
    and a.first_seen_at > now() - interval '30 days'
  order by array_position(array['D0','B0','15'], a.announce_type), c.score desc
  limit p_limit;
$$;
revoke execute on function announcements_to_enrich(text[], integer, integer) from public, anon, authenticated;

-- Set a department's real name everywhere it shows.
create or replace function set_department_name(p_code text, p_name text)
returns void
language sql
set search_path = ''
as $$
  update public.departments set name = p_name where code = p_code and name like 'หน่วยงานรหัส %';
  update public.announcements set dept_name = p_name where dept_code = p_code and dept_name like 'หน่วยงานรหัส %';
$$;
revoke execute on function set_department_name(text, text) from public, anon, authenticated;
