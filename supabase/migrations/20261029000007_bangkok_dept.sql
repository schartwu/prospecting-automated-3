-- กรุงเทพมหานคร has a 7-digit deptId (3100001) that the night sweep (4-digit codes) never finds, so its
-- announcements only came through the nationwide feed (20 latest of the whole country) and most were missed,
-- e.g. 69109124627 had its D0 but not its 15/B0. Probed 29 Oct 2026 (scripts/probe_dept.py): deptId=3100001
-- answers with 20 items per type; the daily collection now reads it like any other department.
insert into departments (code, param, name, source, active)
values ('3100001', 'deptId', 'กรุงเทพมหานคร', 'manual', true)
on conflict do nothing;
