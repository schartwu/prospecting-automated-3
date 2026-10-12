-- Where a run's raw data came from (e.g. 'discovery/types/2026-10-09/1901'), so loading is idempotent.
alter table collect_runs add column source text unique;
