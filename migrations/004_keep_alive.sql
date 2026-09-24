-- Keep-alive endpoint for the GitHub Actions workflow. Supabase pauses free
-- projects after ~7 days without database activity, and 003 removed anon's
-- table access. This function does a real table read as its owner but returns
-- only a boolean, so anon still cannot see any rows.
create or replace function public.keep_alive()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.profile);
$$;

revoke all on function public.keep_alive() from public, anon, authenticated, service_role;
grant execute on function public.keep_alive() to anon;

-- Make PostgREST expose the new function without waiting for a restart.
notify pgrst, 'reload schema';
