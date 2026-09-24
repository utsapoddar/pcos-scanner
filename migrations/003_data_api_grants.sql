-- The Streamlit app is the only database client. It uses the server-side
-- service-role key, so browser-facing roles must not reach these private tables.
-- Explicit grants are required for tables created after Supabase's 2026-10-30
-- Data API default-privilege change.

revoke all on table public.profile from anon, authenticated, service_role;
grant select, insert, update on table public.profile to service_role;

revoke all on table public.saved_foods from anon, authenticated, service_role;
grant select, insert, update, delete on table public.saved_foods to service_role;

revoke all on table public.personalization_cache from anon, authenticated, service_role;
grant select, insert, update on table public.personalization_cache to service_role;

-- Migration bookkeeping is accessed only over the direct Postgres connection.
revoke all on table public.schema_migrations from anon, authenticated, service_role;
