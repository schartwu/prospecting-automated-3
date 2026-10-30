-- Monthly sweep for local-government codes (local-sweep.yml, scripts/probe_local.py --save) on the 1st at
-- 19:30 Bangkok, after the daily collection. Also once on 30 Oct 2026 (the job removes itself).
select cron.schedule('egp-local-sweep', '30 12 1 * *', $$select public.trigger_workflow('local-sweep.yml')$$);
select cron.schedule('egp-local-sweep-once', '30 12 30 10 *',
  $$select public.trigger_workflow('local-sweep.yml'); select cron.unschedule('egp-local-sweep-once')$$);
