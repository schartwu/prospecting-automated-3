-- Generic "start a GitHub workflow" used by both cron jobs (GitHub's own schedule starts runs 6-9 h late).
create or replace function trigger_workflow(p_workflow text, p_inputs jsonb default '{}'::jsonb)
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
    raise notice 'github_actions_token not in Vault; % not triggered', p_workflow;
    return null;
  end if;
  -- Returns the pg_net request id; the response lands in net._http_response (204 = dispatched).
  return net.http_post(
    url := 'https://api.github.com/repos/schartwu/prospecting-automated-3/actions/workflows/'
           || p_workflow || '/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'egp-alert-v3-cron'),
    body := jsonb_build_object('ref', 'main', 'inputs', p_inputs)
  );
end;
$$;
revoke execute on function trigger_workflow(text, jsonb) from public, anon, authenticated;

create or replace function trigger_morning_digest()
returns bigint
language sql
security definer
set search_path = ''
as $$
  select public.trigger_workflow('digest.yml', '{"args": "--send"}'::jsonb);
$$;

-- 18:00 Bangkok every day: collect -> load -> classify -> read documents (~2.5 h).
select cron.schedule('egp-daily-pipeline', '0 11 * * *', $$select public.trigger_workflow('daily.yml')$$);
