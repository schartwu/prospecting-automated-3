-- health.py warns the admin when the database passes 350 MB (the Free plan stops writes at 500 MB).
create or replace function db_size_mb()
returns integer
language sql
stable
set search_path = ''
as $$
  select (pg_database_size(current_database()) / 1048576)::integer;
$$;
revoke execute on function db_size_mb() from public, anon, authenticated;
