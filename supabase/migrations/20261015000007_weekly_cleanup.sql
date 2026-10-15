-- Keep the database well under the Free Plan's 500 MB (read-only above that). Approved 2026-10-15.
-- At ~1,000 new announcements a day (~3 kB each) it would otherwise fill in about 7 months.
--
-- Weekly:
--   1. delete announcements older than 60 days that are not relevant to OfficeMate (about 85% of all
--      rows); their classifications/details go with them (on delete cascade). The RSS feed only
--      repeats items for about a week, so nothing comes back as "new".
--   2. keep relevant announcements forever, with budgets and verdicts.
--   3. empty the raw RSS copy (`raw`) after 14 days; the same data is in the other columns.
--   4. drop AI quota counters older than 30 days.
create or replace function cleanup_old_data()
returns jsonb
language plpgsql
set search_path = ''
as $$
declare
  v_deleted integer;
  v_raw_cleared integer;
  v_ai integer;
begin
  delete from public.announcements a
  where a.first_seen_at < now() - interval '60 days'
    and not exists (select 1 from public.classifications c where c.announcement_id = a.id and c.relevant);
  get diagnostics v_deleted = row_count;

  update public.announcements set raw = '{}'::jsonb
  where first_seen_at < now() - interval '14 days' and raw <> '{}'::jsonb;
  get diagnostics v_raw_cleared = row_count;

  delete from public.ai_usage where day < current_date - 30;
  get diagnostics v_ai = row_count;

  return jsonb_build_object('announcements_deleted', v_deleted, 'raw_cleared', v_raw_cleared,
                            'ai_usage_deleted', v_ai, 'db_size', pg_size_pretty(pg_database_size(current_database())));
end;
$$;
revoke execute on function cleanup_old_data() from public, anon, authenticated;

-- Sunday 02:00 Bangkok (Saturday 19:00 UTC): no pipeline or digest is running then.
select cron.schedule('egp-weekly-cleanup', '0 19 * * 6', $$select public.cleanup_old_data()$$);
