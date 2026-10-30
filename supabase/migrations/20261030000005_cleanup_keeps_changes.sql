-- Cancellations and changes (D1, D2, W1, W2) are never classified (scripts/classify.py), so the 60-day rule
-- deleted them even when their project is a kept lead, and the web app would stop showing that lead as
-- cancelled or its winner as withdrawn. Keep those of projects that have a relevant announcement.
-- Nothing was lost before this fix: the data starts on 2 Oct 2026.
create or replace function cleanup_old_data()
returns jsonb
language plpgsql
set search_path = ''
as $$
declare v_deleted integer; v_raw_cleared integer; v_ai integer; v_visits integer;
begin
  delete from public.announcements a
  where a.first_seen_at < now() - interval '60 days'
    and not exists (select 1 from public.classifications c where c.announcement_id = a.id and c.relevant)
    and not (a.announce_type in ('D1', 'D2', 'W1', 'W2') and a.project_no is not null
             and exists (select 1 from public.announcements k
                         join public.classifications c on c.announcement_id = k.id and c.relevant
                         where k.project_no = a.project_no));
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
end; $$;
