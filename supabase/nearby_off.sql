-- Nobody's location is readable by anyone else while the map and Nearby are off.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it.
--
-- WHAT WAS WRONG
--
-- public.user_locations holds the live location the people map uploads. Its
-- read rules were "Anyone can read locations" (USING true, for every role,
-- signed out included) and "viewable by authenticated users". So any visitor
-- could ask the API for every shared location, and the app's "who can see my
-- location" setting was never enforced anywhere but on the phone. There were
-- also five overlapping rules for writing your own row.
--
-- THE FIX
--
-- The map and Nearby are switched off (TF_FEATURE_NEARBY), and the app no
-- longer uploads a location. Here: one rule, your own row only, for reading
-- and writing, and the table emptied because nothing should be kept while the
-- feature is off. It held 0 rows on 2026-10-18.
--
-- BEFORE SWITCHING NEARBY BACK ON: a SELECT rule that enforces who may see a
-- location (followers, close friends) has to exist in the database. "Anyone"
-- must never come back.
--
-- Applied to production: NOT YET. (Fill the date on apply.)

begin;

drop policy if exists "Anyone can read locations" on public.user_locations;
drop policy if exists "User locations are viewable by authenticated users" on public.user_locations;
drop policy if exists "Users can delete their own location" on public.user_locations;
drop policy if exists "Users can update their own location" on public.user_locations;
drop policy if exists "Users can upsert their own location" on public.user_locations;
drop policy if exists "users can upsert own location" on public.user_locations;
drop policy if exists "Users can manage their own location" on public.user_locations;
drop policy if exists "Own location only" on public.user_locations;

create policy "Own location only"
    on public.user_locations for all to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

delete from public.user_locations;

commit;

-- ---------------------------------------------------------------------------
-- CHECK (read-only)
-- ---------------------------------------------------------------------------
-- select policyname, cmd, roles::text, qual from pg_policies
--  where schemaname = 'public' and tablename = 'user_locations';
-- Expect one row: "Own location only".

-- ---------------------------------------------------------------------------
-- ROLLBACK: deliberately not provided for the "Anyone can read" rule. If the
-- map returns, write an audience rule instead (see above).
-- ---------------------------------------------------------------------------
