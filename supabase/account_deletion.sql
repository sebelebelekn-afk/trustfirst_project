-- Deleting an account deletes what the Terms say it deletes.
--
-- Applied to the Supabase project, not to Django, so nothing in this repository
-- runs it. /api/account/delete/ calls it with the service key.
--
-- WHAT WAS WRONG
--
-- "Delete my account" ran in the browser. It deleted the profile row (posts,
-- comments, likes, follows and stories went with it) and the messages the person
-- sent, then signed out. Left behind: the sign-in record with the email address
-- and password hash, every uploaded file (profile pictures, post photos and
-- videos, stories, chat files, voice notes), and rows in tables the browser
-- never touched. The Terms say "the data goes from our systems rather than being
-- hidden and kept". It did not.
--
-- THE FIX
--
-- tf_delete_account(user) does the database part in one transaction, so it
-- either all happens or none of it does. It:
--   * refuses an account with payment records (wallet transactions,
--     withdrawals, coin history, revenue, a balance or coins). The law makes us
--     keep those, and deleting the sign-in record would break them. Those are
--     closed by hand, on request.
--   * returns the account's files, so the server can remove them through the
--     storage API (deleting storage rows here would orphan the bytes).
--   * unhooks what other people keep: a chat the account started stays for the
--     others in it, a reply to the account's comment stays, a quote stays, a
--     report filed against the account stays for moderation.
--   * deletes everything else that belongs to the account, including rows tied
--     only to the sign-in record, so removing that record afterwards cannot be
--     blocked or leave anything behind.
--
-- The server then deletes the files (Supabase storage and R2) and the sign-in
-- record itself through the auth admin API.
--
-- Reviewed against every foreign key in the public schema on 2026-10-18 and
-- tested on a local PostgreSQL 16 copy of that structure.
--
-- Applied to production: 2026-10-18, pasted into the Supabase SQL editor by the
-- owner (paste_in_order_2026-10-18.sql) and checked the same day against
-- pg_policies, pg_proc and storage.buckets.

begin;

create or replace function public.tf_delete_account(p_user uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_files jsonb;
begin
    -- Only the server may run this: a signed-in caller carries a user id.
    if auth.uid() is not null then
        raise exception 'not allowed';
    end if;
    if p_user is null or not exists (select 1 from public.users where id = p_user) then
        return jsonb_build_object('ok', false, 'reason', 'not_found');
    end if;
    if p_user = 'edd1e000-0000-4000-8000-000000000001'::uuid then
        return jsonb_build_object('ok', false, 'reason', 'system_account');
    end if;
    if exists (select 1 from public.wallet_transactions where user_id = p_user)
       or exists (select 1 from public.withdrawals where user_id = p_user)
       or exists (select 1 from public.coin_transactions where user_id = p_user)
       or exists (select 1 from public.platform_revenue where from_user = p_user or to_user = p_user)
       or exists (select 1 from public.wallets where user_id = p_user and coalesce(balance, 0) <> 0)
       or exists (select 1 from public.users where id = p_user and coalesce(coins, 0) <> 0) then
        return jsonb_build_object('ok', false, 'reason', 'payment_records');
    end if;

    select coalesce(jsonb_agg(jsonb_build_object('bucket', bucket_id, 'name', name)), '[]'::jsonb)
      into v_files
      from storage.objects
     where (storage.foldername(name))[1] = p_user::text or owner = p_user;

    -- What other people keep, unhooked from this account.
    update public.conversations set created_by = null where created_by = p_user;
    update public.users set parent_id = null where parent_id = p_user;
    update public.users set gold_badge_granted_by = null where gold_badge_granted_by = p_user;
    update public.groups set admin_id = null where admin_id = p_user;
    update public.comments set parent_comment_id = null
     where user_id <> p_user
       and parent_comment_id in (select id from public.comments where user_id = p_user);
    -- A plain repost has nothing of its own; a post that only pointed here keeps its words.
    delete from public.posts
     where post_type = 'repost' and user_id <> p_user
       and original_post_id in (select id from public.posts where user_id = p_user);
    update public.posts set original_post_id = null
     where user_id <> p_user
       and original_post_id in (select id from public.posts where user_id = p_user);
    update public.harassment_flags set message_id = null
     where message_id in (select id from public.messages where sender_id = p_user);
    update public.trust_circles set members = array_remove(members, p_user) where p_user = any(members);
    update public.kids_account_applications set child_user_id = null where child_user_id = p_user;
    update public.kids_account_applications set reviewed_by = null where reviewed_by = p_user;
    update public.reports set reviewed_by = null where reviewed_by = p_user;
    update public.reports set reporter_id = null where reporter_id = p_user;
    update public.verification_applications set reviewed_by = null where reviewed_by = p_user;
    update public.withdrawals set decided_by = null where decided_by = p_user;
    update public.feedback set user_id = null where user_id = p_user;
    update public.group_activity_log set actor_id = null where actor_id = p_user;
    update public.group_admin_rules set created_by = null where created_by = p_user;

    -- Everything else that is the account's.
    delete from public.notifications where actor_id = p_user;
    delete from public.messages where sender_id = p_user;
    delete from public.shared_media where sender_id = p_user;
    delete from public.screenshot_events where user_id = p_user;
    delete from public.account_lock_events where user_id = p_user;
    delete from public.harassment_flags where reporter_id = p_user or reported_user_id = p_user;
    delete from public.gov_verification_requests where user_id = p_user;
    delete from public.child_activity_log where parent_id = p_user or child_id = p_user;
    delete from public.parent_approvals where parent_id = p_user or child_id = p_user;
    delete from public.parent_link_requests where parent_id = p_user or child_id = p_user;
    delete from public.call_signals where sender_id = p_user;
    delete from public.calls where caller_id = p_user or callee_id = p_user;
    delete from public.session_logs where user_id = p_user;
    delete from public.channels where owner_id = p_user;
    delete from public.post_views where viewer_id = p_user;
    delete from public.clip_views where viewer_id = p_user;
    delete from public.story_views where viewer_id = p_user
        or story_id in (select id from public.stories where user_id = p_user);
    delete from public.comments where clip_id in (select id from public.trustclips where user_id = p_user);
    delete from public.trustclips where user_id = p_user;
    delete from public.clip_likes where user_id = p_user;
    delete from public.clip_sticker_responses where user_id = p_user;
    delete from public.channel_followers where user_id = p_user;
    delete from public.follow_requests where requester_id = p_user or target_id = p_user;
    delete from public.group_member_prefs where user_id = p_user;
    delete from public.hide_story_from where owner_id = p_user or hidden_user_id = p_user;
    delete from public.live_sessions where user_id = p_user;
    delete from public.login_attempts where user_id = p_user;
    delete from public.recently_deleted_stories where user_id = p_user;
    delete from public.trust_circles where user_id = p_user;
    delete from public.user_locations where user_id = p_user;
    delete from public.verification_applications where user_id = p_user;
    delete from public.kids_account_applications where applicant_id = p_user;
    delete from public.watch_history where user_id = p_user;
    delete from public.wallets where user_id = p_user;

    -- The profile. Posts, comments, likes, follows, stories, notifications, keys,
    -- devices, Eddie chats and the rest go with it.
    delete from public.users where id = p_user;
    delete from public.profiles where id = p_user;

    return jsonb_build_object('ok', true, 'files', v_files);
end;
$$;

revoke all on function public.tf_delete_account(uuid) from public, anon, authenticated;
grant execute on function public.tf_delete_account(uuid) to service_role;

commit;

-- ---------------------------------------------------------------------------
-- CHECK (read-only)
-- ---------------------------------------------------------------------------
-- select has_function_privilege('authenticated', 'public.tf_delete_account(uuid)', 'execute') as users_can_call,
--        has_function_privilege('service_role', 'public.tf_delete_account(uuid)', 'execute') as server_can_call;
-- Expect false, true.

-- ---------------------------------------------------------------------------
-- ROLLBACK
-- ---------------------------------------------------------------------------
-- drop function if exists public.tf_delete_account(uuid);
