-- 2026-10-28: the repository is now schartwu/prospecting-automated-kg.
create or replace function public.trigger_workflow(p_workflow text, p_inputs jsonb default '{}'::jsonb)
returns bigint
language plpgsql
security definer
set search_path to ''
as $function$
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
    url := 'https://api.github.com/repos/schartwu/prospecting-automated-kg/actions/workflows/'
           || p_workflow || '/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_token,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'egp-alert-v3-cron'),
    body := jsonb_build_object('ref', 'main', 'inputs', p_inputs)
  );
end;
$function$;
