-- Which version of the Terms each account has acknowledged.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it. Written down here because the app depends on the column and a schema
-- change that exists only inside a database is invisible to everyone reading
-- the code that needs it. Re-running is safe.
--
--
-- HOW THE NOTICE WORKS
--
-- settings.TERMS_VERSION is the version that is live, and rides along in
-- /api/config. users.terms_accepted_version is what each account last
-- acknowledged. They differ, the app shows the notice once; pressing Got it
-- writes the live version to the row. Bumping the environment variable is
-- therefore the whole release process for a Terms change.
--
--
-- WHY A COLUMN RATHER THAN localStorage
--
-- A legal acknowledgement belongs to the person, not to a handset. Stored per
-- device it would ask again on a second phone, forget itself when somebody
-- clears their browser, and leave nothing on the server that says who agreed to
-- what. A column answers the only question anyone ever asks of such a record.
--
--
-- WHY THE BACKFILL
--
-- Every existing account is set to the version that was live when this was
-- applied. Without it they would all have been shown "we have updated our
-- Terms" on next open, which would not have been true - nothing had changed.
-- The notice should fire the first time the version is genuinely bumped, and a
-- notice that cries wolf is worse than no notice.

alter table public.users add column if not exists terms_accepted_version text;

-- users carries column-level grants (see lock_down_users_columns.sql), so a new
-- column is invisible and unwritable to the app until it is named here.
grant select (terms_accepted_version) on public.users to authenticated;
grant update (terms_accepted_version) on public.users to authenticated;
grant insert (terms_accepted_version) on public.users to authenticated;

-- Safe to re-run: only ever fills in accounts that have no value yet.
update public.users
   set terms_accepted_version = '2026-09-14'
 where terms_accepted_version is null;
