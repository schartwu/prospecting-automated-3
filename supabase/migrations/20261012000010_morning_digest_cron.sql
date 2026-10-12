-- 07:30 Bangkok, Mon-Fri: start the "Morning digest" GitHub workflow with --send.
-- GitHub's own schedule can start hours late; pg_cron fires on time and just dispatches the workflow.
--
-- Needs a GitHub fine-grained token (this repo only, Actions: read & write) stored in Vault under the
-- name 'github_actions_token'. Until it exists the job does nothing.
create extension if not exists pg_cron;
create extension if not exists pg_net;

create or replace function trigger_morning_digest()
returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_token text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'github_actions_token';
  if v_token is null then
    raise notice 'github_actions_token not in Vault yet; morning digest not triggered';
    return null;
  end if;
  -- Returns the pg_net request id; the response lands in net._http_response (204 = dispatched).
  return net.http_post(
    url := 'https://api.github.com/repos/schartwu/prospecting-automated-3/actions/workflows/digest.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'egp-alert-v3-cron'),
    body := '{"ref": "main", "inputs": {"args": "--send"}}'::jsonb
  );
end;
$$;

revoke execute on function trigger_morning_digest() from public, anon, authenticated;

select cron.schedule('egp-morning-digest', '30 0 * * 1-5', $$select public.trigger_morning_digest()$$);
