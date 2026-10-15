-- The e-GP RSS server did not answer during the working day either: on 2026-10-15 the 14:00 recheck got
-- 0 of 35 feeds and the 16:30 one 1 of 35. RSS work only succeeds from about 17:00, so the daytime
-- re-reads are removed. recheck.yml stays for manual evening use.
select cron.unschedule('egp-midday-recheck');
select cron.unschedule('egp-afternoon-recheck');
