-- Anybody signed in could make themselves an admin, and mint their own coins.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it. Written down here because a privilege that exists only inside a
-- database is invisible, and this one is the difference between a wallet and a
-- free-for-all. Re-running it is safe.
--
--
-- WHAT WAS WRONG
--
-- public.users had RLS enabled and a sensible-looking policy:
--
--     users_update  USING (auth.uid() = id)  WITH CHECK (auth.uid() = id)
--
-- which says "you may update your own row" and is correct as far as it goes.
-- The gap is that RLS in Postgres is row-level only. It decides WHICH rows you
-- may touch and says nothing about WHICH COLUMNS. Column protection comes from
-- grants, and both anon and authenticated held a blanket table-level UPDATE.
--
-- So every column of your own row was yours to set, including these:
--
--     is_admin    -> set it true, and _require_admin in core/api_views.py then
--                    reads it back and believes you. That endpoint returns
--                    every pending withdrawal with the account holder, bank and
--                    account number attached, and its sibling marks withdrawals
--                    paid. One UPDATE from any account and every user's banking
--                    details are readable.
--     coins       -> set it to anything. tf_cash_out_coins converts coins to
--                    wallet Rands at 0.0999 each, and tf_request_withdrawal
--                    turns wallet Rands into a payout request against a real
--                    bank account. Minted coins were therefore a straight line
--                    to real money leaving the business.
--     is_banned   -> unban yourself.
--     id          -> point your row at somebody else.
--
-- Nothing had been exploited: withdrawals and platform_revenue were both empty
-- and no account other than the owner's had is_admin set. It was found while
-- checking whether withdrawals worked, before the app had any real users.
--
--
-- THE FIX
--
-- Take back the blanket UPDATE and hand back only the columns the app actually
-- writes. The four above are simply not among them, so the policy above now
-- means what it always appeared to mean.
--
-- This does not break anything that legitimately changes coins. spend_coins,
-- send_gift, tf_buy_coins and tf_cash_out_coins are all SECURITY DEFINER and
-- owned by postgres, so they run with the owner's rights and never needed the
-- caller to hold this grant. The Django server uses the service key, which is
-- also unaffected. What changed is only what a browser holding a user's own
-- token may write directly.
--
-- anon loses UPDATE entirely and is not granted anything back. RLS already
-- blocked it — auth.uid() is null, so no row matched — but a signed-out caller
-- having write grants on a user table at all was never intended.

revoke update on public.users from anon, authenticated;

grant update (
  email, username, full_name, account_type, stripe_identity_id, verified,
  badge_tier, avatar_url, cover_url, bio, parent_id, trust_score, is_locked,
  locked_at, lock_reason, last_seen, created_at, updated_at,
  password_changed_at, privacy_settings, phone, website, location,
  verification_method, gold_badge_reason, gold_badge_granted_by,
  gold_badge_granted_at, is_child, gov_email, gov_position, gov_department,
  gov_employee_id, gov_verified, face_verified, id_verified, followers_count,
  following_count, post_count, display_name, is_kid, follower_count,
  badge_status, liveness_verified, liveness_steps, pronouns, profile_links,
  website_url, ai_label, country, is_bot, birth_date
) on public.users to authenticated;


-- STILL OPEN, DELIBERATELY, BECAUSE THE APP WRITES THEM TODAY
--
-- These are granted back above and should not stay that way. Each needs a
-- server endpoint before the grant can go, and taking them now would break
-- working screens:
--
--   is_locked, locked_at, lock_reason
--       A user can lock their own account (feed.js) and an admin unlocks it
--       from the browser (admin.js). The same grant lets somebody an admin has
--       locked unlock themselves.
--
--   verified, badge_status, badge_tier, trust_score,
--   gov_verified, face_verified, id_verified, liveness_verified
--       Admin verification writes these straight from the browser, so a user
--       can award themselves any badge the app can display — on a platform
--       whose whole proposition is that the badge means something.
--
-- Neither is a route to money, which is why they are not fixed in the same
-- breath as the ones above.


-- Checking it later:
--
--   select grantee, string_agg(column_name, ', ' order by column_name)
--     from information_schema.column_privileges
--    where table_schema='public' and table_name='users'
--      and privilege_type='UPDATE' and grantee in ('anon','authenticated')
--    group by grantee;
--
-- is_admin, coins, is_banned and id must not appear, and anon must not appear
-- at all.
