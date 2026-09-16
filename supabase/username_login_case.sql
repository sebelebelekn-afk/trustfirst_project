-- Username login was case-sensitive on the way in.
--
-- Applied to production 2026-09-16. Recorded here because the rest of the
-- schema lives in this folder and a function nobody can find is a function
-- somebody eventually drops.
--
-- The symptom: anybody whose username has a capital letter in it could not log
-- in with it. The login screen checks the username exists before asking for a
-- password, and that check was:
--
--     sb.from('users').select('username').eq('username', username.toLowerCase())
--
-- Postgres equality is case-sensitive, so a stored "TrustFirst" never matched a
-- lowercased "trustfirst". Those users were told "No account found with that
-- username", shaken off the screen, and never got as far as typing a password.
-- Their password was never wrong.
--
-- Signup lowercases usernames today, so only accounts predating that rule are
-- affected -- but they are real accounts and this locked them out of the
-- username path entirely.
--
-- tf_login_email() already compared lower() on both sides and was never the
-- problem. This is the same treatment for the existence check, returning a
-- boolean rather than a row, so it hands back strictly less than the table read
-- it replaces. The leading @ is trimmed because people type their username the
-- way the app displays it.

create or replace function public.tf_username_taken(uname text)
returns boolean
language sql
security definer
set search_path to 'public', 'pg_temp'
as $$
    select exists (
        select 1 from public.users
        where lower(username) = lower(ltrim(trim(uname), '@'))
    );
$$;

revoke all on function public.tf_username_taken(text) from public;
grant execute on function public.tf_username_taken(text) to anon, authenticated;

-- Checks:
--   select public.tf_username_taken('TrustFirst');   -- true
--   select public.tf_username_taken('trustfirst');   -- true
--   select public.tf_username_taken('@TrustFirst');  -- true
--   select public.tf_username_taken('nobody_here');  -- false
--   select public.tf_username_taken('');             -- false
